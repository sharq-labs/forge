"""Genesis-lite v0.3 freeze-readiness gate (read-only; it never freezes, runs a campaign or edits a tracked file).

    python -m benchmarks.genesis_lite.v0_3.readiness [--approvals PATH]

It runs the v0.3 test files itself (:func:`collect_evidence`) and binds the result to the committed HEAD. A ledger row
counts as FIXED only when EVERY test it names (:data:`REQUIRED_TESTS`, exact function names, every parametrization)
was collected and PASSED in that run, on a clean tree at that HEAD. A row's label alone is never evidence, and a new
test with a matching prefix proves nothing. Evidence passed to :func:`check` by a caller is the caller's claim; only the
CLI collects it.

Statuses, in order of precedence:

* ``BLOCKED_TECHNICAL``: something the code must still fix or prove. Examples: the preregistration does not rebuild;
  an earlier identity moved; the escrow half is missing; evaluator and escrow disagree; a technical row has no passing
  evidence; the one-attempt registry fails its self-test; the evidence is not from a clean committed HEAD.
* ``READY_TO_FREEZE_PENDING_OWNER``: every technical condition holds, but owner decisions, an owner-set value (w, root
  commitment, environment manifest, candidate) or OD-3 are missing. Each reason is listed exactly.
* ``PASS``: everything holds, every decision in :data:`REQUIRED_APPROVALS` is APPROVED for THIS preregistration digest
  (the scoring decision also names the bound w), and OD-3 names this HEAD.

PASS is never reported with a pending owner decision. The approval record is the OWNER's file. This module defines its
shape and never writes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from .. import preregistration as v02p
from . import evaluator as v03e
from . import preregistration as v03p

PASS, PENDING_OWNER, BLOCKED = "PASS", "READY_TO_FREEZE_PENDING_OWNER", "BLOCKED_TECHNICAL"
FIXED, NOT_A_BLOCKER = "FIXED_AND_TESTED", "NOT_A_REAL_BLOCKER"
BLOCKED_OD3, OWNER = "SPECIFIED_BLOCKED_BY_OD3", "OWNER_DECISION_REQUIRED"
V0_2_SHA256 = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"
APPROVALS_PATH = v03p.PREREG_PATH.with_name("genesis_lite_v0_3.owner_approvals.json")
TEST_FILES = ("tests/genesis_lite/test_genesis_lite_v0_3_amendment.py",
              "tests/genesis_lite/test_genesis_lite_v0_3_blockers.py",
              "tests/genesis_lite/test_genesis_lite_v0_3_escrow_fda05.py")
#: the consolidated owner decision set (decision record section 5)
REQUIRED_APPROVALS = ("D1-scoring", "D2-significance", "D3-baselines-and-tells", "D4-identity-freeze", "D5-deployment",
                      "D6-evaluator", "D7-budget-and-machine", "OD-3")

#: name -> (status, test prefixes that must pass, note). FIXED / NOT_A_BLOCKER rows are verified against evidence.
LEDGER: dict[str, tuple[str, tuple[str, ...], str]] = {
    "FDA-05 evaluator half": (FIXED, ("test_fda05_",), "bracket route bounded; w bound to the preregistration"),
    "FDA-06": (FIXED, ("test_fda06_",), "cap over every law-credit kind incl. indistinguishable"),
    "O-1": (FIXED, ("test_o1_",), "sign-flip p; bootstrap for the bound only; Holm unchanged"),
    "FDA-18 (process memory and temp files)": (FIXED, ("test_fda18_",), "one process and temp dir per card"),
    "FDA-18 residual (same-account files, helper processes)": (
        OWNER, (), "D5 / OD-20: the cross_card_state and persistence attacks must be REFUSED in the deployment"),
    "FDA-19 (Genesis-lite secret inventory)": (FIXED, ("test_fda19_",), "proposer-side secret_scan; the certified "
                                                                        "isolation_probe is not extended"),
    "FDA-21": (FIXED, ("test_fda21_",), "corrected-dof arms ADDED beside the v0.2 arms"),
    "FDA-22": (FIXED, ("test_fda22_",), "tell declared, law_form measured; equalising the priors is a D3 option"),
    "pilot P-1 (always_law)": (NOT_A_BLOCKER, ("test_pilot_p1_",), "solved by the v0.1 joint endpoint"),
    "pilot P-2 (control cells)": (FIXED, ("test_pilot_p2_",), "CONTROL_SOLVED cap"),
    "pilot P-3 (out-of-family share)": (FIXED, ("test_pilot_p3_",), "FDA-06 cap"),
    "readiness P-1/P-2 (isolation deployment, escrow out of process)": (OWNER, (), "D5 / OD-20"),
    "readiness P-3 (attack arms)": (FIXED, ("test_readiness_p3_",), "suite exists; verdicts come from the deployment"),
    "P-4 formal driver, candidate in the attempt": (FIXED, ("test_p4_",), "review 2026-10-20 finding 1"),
    "P-5 environment manifest": (FIXED, ("test_p5_",), "measured inside bind for the formal tier"),
    "one attempt per root": (FIXED, ("test_attempt_",), "registry + publication + post-reveal verify_attempt"),
    "pass route with an arbitrary partner (ODC-05d)": (OWNER, (), "D1"),
    "no preregistered power analysis (review note 13)": (OWNER, (), "D2: the claimable region may be small"),
}


#: ledger row -> the exact tests that prove it (generated from the test files; a renamed test fails the row)
REQUIRED_TESTS: dict[str, tuple[str, ...]] = {
    'FDA-05 evaluator half': (
        'test_fda05_v0_2_credits_one_vacuous_pair_for_two_mutually_exclusive_truths',
        'test_fda05_v0_3_scores_the_vacuous_pair_a_miss_for_both_truths',
        'test_fda05_v0_3_keeps_the_informative_pair_whatever_w_is',
        'test_fda05_v0_3_keeps_the_audit_controls',
        'test_fda05_bracket_credit_survives_inside_the_bound_and_only_there',
        'test_fda05_w_is_an_owner_decision_never_a_default',
        'test_fda05_v0_3_fails_closed_against_an_escrow_that_still_credits_the_vacuous_pair',
        'test_fda05_a_caller_chosen_w_is_refused_unless_it_is_the_preregistered_one',
        'test_fda05_v0_3_changes_the_rule_not_the_credit_table',
        'test_fda05_v0_3_evaluator_imports_nothing_but_the_standard_library',
    ),
    'FDA-06': (
        'test_fda06_v0_2_leaves_an_out_of_family_spurious_world_uncapped',
        'test_fda06_v0_3_caps_every_law_credit_kind_out_of_family',
        'test_fda06_v0_3_does_not_cap_law_credit_in_family',
        'test_fda06_v0_3_refuses_a_law_credit_kind_without_its_family_flag',
        'test_fda06_the_capped_kinds_are_derived_from_the_frozen_credit_table',
    ),
    'O-1': (
        'test_o1_v0_2_bootstrap_fraction_is_not_a_valid_p_value',
        'test_o1_v0_3_p_is_super_uniform_under_the_sign_symmetric_null',
        'test_o1_v0_3_exact_p_equals_brute_force_enumeration',
        'test_o1_v0_3_monte_carlo_path_is_valid_deterministic_and_agrees_with_exact',
        'test_o1_v0_3_refuses_differences_outside_the_credit_lattice',
        'test_o1_holm_is_unchanged',
        'test_o1_v0_3_lift_decision_uses_sign_flip_p_and_claims_nothing_while_draft',
    ),
    'FDA-18 (process memory and temp files)': (
        'test_fda18_v0_2_one_process_carries_state_across_the_cards_of_a_campaign',
        'test_fda18_v0_3_a_fresh_proposer_process_per_card_keeps_nothing_between_cards',
        'test_readiness_p3_per_card_temp_dirs_hold_nothing_but_same_account_files_elsewhere_do',
    ),
    'FDA-19 (Genesis-lite secret inventory)': (
        'test_fda19_the_secret_scan_finds_every_inventory_item_and_nothing_in_clean_files',
        'test_fda19_the_scan_finds_wrapped_utf16_and_streamed_secrets',
        'test_fda19_the_scan_does_not_flag_the_benchmark_sources',
    ),
    'FDA-21': (
        'test_fda21_v0_2_residual_variance_is_biased_by_the_fitted_parameters',
        'test_fda21_v0_3_residual_variance_is_unbiased',
        'test_fda21_v0_3_replicate_noise_uses_mean_zero_pairs',
        'test_fda21_v0_3_keeps_every_v0_2_arm_and_adds_corrected_variants',
    ),
    'FDA-22': (
        'test_fda22_the_generator_tell_exists_and_v0_3_declares_it',
        'test_fda22_law_form_classifies_every_generator_form',
    ),
    'pilot P-1 (always_law)': (
        'test_pilot_p1_a_floor_arm_that_always_proposes_gains_nothing_under_the_joint_endpoint',
    ),
    'pilot P-2 (control cells)': (
        'test_pilot_p2_v0_2_credits_a_control_cell_that_a_non_discoverer_already_solves',
        'test_pilot_p2_v0_3_caps_control_cells_that_a_registered_arm_solves',
        'test_pilot_p2_the_binary_lower_bound_is_the_exact_bootstrap_quantile',
    ),
    'pilot P-3 (out-of-family share)': (
        'test_pilot_p3_a_gain_only_in_out_of_family_worlds_is_capped',
    ),
    'readiness P-3 (attack arms)': (
        'test_readiness_p3_network_attack_reaches_a_listener_and_is_untestable_without_a_target',
        'test_readiness_p3_root_file_and_run_log_attacks_read_what_the_command_line_names',
        'test_readiness_p3_package_write_probe_writes_nothing',
        'test_readiness_p3_the_deployment_is_verified_only_if_every_channel_is_refused_and_the_scan_is_clean',
        'test_readiness_p3_the_suite_through_per_card_processes_is_not_verified_on_a_same_account_host',
        'test_readiness_p3_per_card_temp_dirs_hold_nothing_but_same_account_files_elsewhere_do',
    ),
    'P-4 formal driver, candidate in the attempt': (
        'test_p4_a_document_that_merely_says_frozen_is_refused',
        'test_p4_the_driver_refuses_the_committed_draft',
        'test_p4_the_driver_refuses_a_retired_or_uncommitted_root_and_a_changed_environment',
        'test_p4_the_driver_runs_every_arm_once_on_every_formal_world_set_and_releases_world_sets_whole',
        'test_p4_a_record_under_another_identity_is_invalid_not_relabelled',
        'test_p4_formal_masters_never_coincide_with_pilot_masters',
        'test_p4_the_root_never_travels_on_the_command_line',
        'test_p4_the_production_runner_is_the_v0_3_harness_and_refuses_a_draft_identity',
        'test_p4_the_sealed_log_is_append_only_and_hash_chained',
        'test_p4_candidate_runs_inside_the_attempt_world_set_major',
        'test_p4_candidate_code_and_name_are_pinned',
        'test_p4_lift_decision_requires_a_clean_post_reveal_verification',
        'test_p4_candidate_dynamic_calls_twins_and_markers',
        'test_p4_candidate_parent_packages_and_ambiguous_files_are_refused',
        'test_p4_candidate_spec_module_and_its_imports_must_be_pinned',
        'test_p4_representation_cap_covers_both_enumeration_arms',
        'test_p4_the_identity_lists_a_fixed_retired_set',
    ),
    'P-5 environment manifest': (
        'test_p5_the_manifest_names_the_interpreter_and_every_imported_distribution',
    ),
    'one attempt per root': (
        'test_attempt_first_formal_attempt_is_admitted_and_a_second_is_refused',
        'test_attempt_a_restart_still_refuses',
        'test_attempt_a_copied_output_directory_or_new_label_or_identity_cannot_bypass',
        'test_attempt_development_roots_stay_apart_from_formal_roots',
        'test_attempt_a_crash_lock_and_a_tampered_registry_fail_closed',
        'test_attempt_the_driver_consumes_the_root_before_any_world',
        'test_attempt_a_revealed_pilot_root_is_refused_before_admission',
        'test_attempt_a_fresh_registry_cannot_reproduce_an_attempt_or_its_worlds',
        'test_attempt_the_evaluator_verifies_the_whole_published_log_after_the_reveal',
        'test_attempt_a_screened_world_set_verifies_only_if_its_screen_rederives',
        'test_attempt_a_whole_record_swap_between_arms_does_not_replay',
    ),
    'v0.3 harness binding': (
        'test_harness_refuses_the_v0_2_preregistration',
        'test_harness_refuses_an_arbitrary_frozen_dict',
        'test_harness_a_formal_binding_never_takes_a_callers_manifest',
        'test_harness_refuses_a_changed_w',
        'test_harness_refuses_a_changed_w_against_a_frozen_bound',
        'test_harness_refuses_a_changed_credit_table',
        'test_harness_refuses_a_changed_environment_manifest',
        'test_harness_refuses_a_modified_evaluator',
        'test_harness_refuses_a_formal_run_of_a_draft_and_a_development_bound_other_than_the_decided_w',
        'test_harness_never_falls_back_without_the_escrow_half',
        'test_harness_a_formal_run_takes_no_hook_path_spec_or_in_process_arm',
        'test_harness_a_formal_run_refuses_an_arm_that_is_neither_registered_nor_the_candidate',
        'test_harness_uses_only_v0_3_scoring',
    ),
}
#: rows proven by tests/genesis_lite/test_genesis_lite_v0_3_escrow_fda05.py, which exists only with the escrow half
ESCROW_TESTS: dict[str, tuple[str, ...]] = {
    'FDA-05 escrow half': (
        'test_escrow_fda05_v0_2_escrow_credits_the_vacuous_pair_for_both_truths',
        'test_escrow_fda05_the_bounded_escrow_misses_the_vacuous_pair_for_both_truths',
        'test_escrow_fda05_controls_honest_hits_inbox_disagreement_misses_narrow_bracket_follows_w',
        'test_escrow_fda05_evaluator_and_escrow_agree_on_every_selfcheck_case',
        'test_escrow_fda05_the_config_digest_seals_w_and_v0_2_is_unchanged',
        'test_escrow_fda05_v0_2_identity_is_untouched_by_the_escrow_half',
        'test_escrow_fda05_the_bounded_escrow_refuses_a_campaign_sealed_under_another_config',
        'test_escrow_fda05_the_bounded_escrow_runs_the_v0_2_score_procedure_unchanged',
    ),
    'v0.3 harness end to end': (
        'test_harness_binds_with_the_escrow_half_and_seals_w_in_the_config',
        'test_harness_an_honest_arm_runs_valid_with_agreement_and_records_its_binding',
        'test_harness_the_vacuous_attack_never_earns_a_bracket_hit_and_both_sides_agree',
        'test_harness_records_of_an_honest_attempt_verify_end_to_end',
        'test_harness_a_forged_credit_or_flag_does_not_verify',
        'test_harness_a_whole_record_swap_between_arms_does_not_verify',
    ),
}


def _escrow_half() -> Any:
    try:
        from engcore.blindfold import pair_bound  # noqa: PLC0415
    except ImportError:
        return None
    return pair_bound


def agreement_cases() -> list[dict[str, Any]]:
    """Evaluator vs escrow on the fixed synthetic R-05 world (:mod:`.selfcheck`); empty without the escrow half."""
    pair_bound = _escrow_half()
    if pair_bound is None:
        return []
    from . import selfcheck  # noqa: PLC0415

    return selfcheck.compare(pair_bound)


def blockers() -> dict[str, tuple[str, tuple[str, ...], str]]:
    rows = dict(LEDGER)
    present = _escrow_half() is not None
    rows["v0.3 harness binding"] = (FIXED, (), "refusals: identity, credit, w, environment, formal lockdown")
    rows["FDA-05 escrow half"] = ((FIXED, (), "engcore.blindfold.pair_bound; UNCERTIFIED (OD-3)")
                                  if present else (BLOCKED_OD3, (), "engcore.blindfold.pair_bound is not in this tree "
                                                   "(branch feat/genesis-lite-v03-escrow-fda05)"))
    rows["v0.3 harness end to end"] = ((FIXED, (), "binds only with the escrow half") if present
                                       else (BLOCKED_OD3, (), "binds only with the escrow half (no fallback)"))
    required = {**REQUIRED_TESTS, **ESCROW_TESTS}
    return {name: (status, required.get(name, ()), note) for name, (status, _prefixes, note) in rows.items()}


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=v03p.HERE, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _head() -> str:
    return (_git("rev-parse", "HEAD") or "").strip()


def collect_evidence(python: str | None = None) -> dict[str, Any]:
    """Run the v0.3 test files that exist in this tree; return {head, clean, tests: {name: outcome}}."""
    root = v02p.ROOT
    files = [f for f in TEST_FILES if (root / f).is_file()]
    if not files:
        return {"head": _head(), "clean": False, "tests": {}, "missing_files": list(TEST_FILES)}
    with tempfile.TemporaryDirectory(prefix="gl-readiness-") as d:
        junit = pathlib.Path(d) / "junit.xml"
        subprocess.run([python or sys.executable, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider",
                        f"--junitxml={junit}", f"--basetemp={pathlib.Path(d) / 'bt'}"], cwd=root, capture_output=True,
                       text=True, check=False)
        tests: dict[str, str] = {}
        if junit.is_file():
            for case in ET.parse(junit).getroot().iter("testcase"):
                tags = {child.tag for child in case}
                tests[f"{case.get('classname', '')}::{case.get('name', '')}"] = (
                    "failed" if tags & {"failure", "error"} else "skipped" if "skipped" in tags else "passed")
    status = _git("status", "--porcelain", "--untracked-files=all")
    return {"head": _head(), "clean": status == "", "tests": tests}


def _row_verified(required: tuple[str, ...], tests: Mapping[str, str]) -> bool:
    for name in required:
        short = {test: test.rsplit("::", 1)[-1] for test in tests}
        hits = [outcome for test, outcome in tests.items() if short[test] == name or short[test].startswith(name + "[")]
        if not hits or any(o != "passed" for o in hits):
            return False
    return bool(required)


def _one_attempt_selftest() -> bool:
    from .registry import AttemptRefused, AttemptRegistry, EvaluatorInbox  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="gl-registry-selftest-") as d:
        digest = hashlib.sha256(b"selftest").hexdigest()
        kwargs = {"root_commitment_sha256": digest, "prereg_sha256": digest, "campaign_set_sha256": digest}
        first = AttemptRegistry(pathlib.Path(d) / "a").admit(tier="formal", **kwargs)
        for tier in ("formal", "development"):
            try:
                AttemptRegistry(pathlib.Path(d) / "a").admit(tier=tier, **kwargs)
            except AttemptRefused:
                continue
            return False
        inbox = EvaluatorInbox(pathlib.Path(d) / "inbox.jsonl")       # a fresh operator registry, same evaluator
        inbox.receive(first)
        try:
            inbox.receive(AttemptRegistry(pathlib.Path(d) / "b").admit(tier="formal", **kwargs))
        except AttemptRefused:
            return True
        return False


def check(approvals_path: pathlib.Path | None = None, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    technical, owner = [], []
    committed = v03p.PREREG_PATH.read_bytes()
    prereg_sha = hashlib.sha256(committed).hexdigest()
    technical += [f"identity: {p}" for p in v03p.committed_doc_problems(committed)]
    for path, sha in ((v02p.V0_PREREG_PATH, v02p.V0_PREREG_SHA256), (v02p.V0_1_PREREG_PATH, v02p.V0_1_PREREG_SHA256),
                      (v02p.PREREG_PATH, V0_2_SHA256)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            technical.append(f"historical identity moved: {path.name}")
    head = _head()
    if not head:
        technical.append("cannot determine HEAD: evidence and OD-3 cannot be bound")
    if evidence is None:
        technical.append("no test evidence in this invocation (run the CLI, which collects it)")
        tests: Mapping[str, str] = {}
    else:
        tests = evidence.get("tests", {})
        if evidence.get("head") != head or not head or evidence.get("clean") is not True:
            technical.append("the test evidence is not from a clean tree at this HEAD")
        bad = sorted(name for name, outcome in tests.items() if outcome != "passed")
        if bad:                                                  # any v0.3 test, required by a row or not
            technical.append(f"{len(bad)} v0.3 test(s) did not pass: {bad[:3]}")
    rows = blockers()
    for name, (status, prefixes, note) in sorted(rows.items()):
        if status in (FIXED, NOT_A_BLOCKER):
            if not _row_verified(prefixes, tests):
                technical.append(f"{name}: claimed {status}, but its {len(prefixes)} named test(s) did not all pass "
                                 f"here")
        elif status == BLOCKED_OD3:
            technical.append(f"{name}: {status} ({note})")
        else:
            owner.append(f"{name}: {status} ({note})")
    if _escrow_half() is not None:
        owner.append("engcore/blindfold/pair_bound.py is certified scope and UNCERTIFIED: OD-3")
    cases = agreement_cases()
    if cases and not all(c["agree"] for c in cases):
        technical.append(f"evaluator and escrow disagree on {sum(not c['agree'] for c in cases)} synthetic case(s)")
    if not _one_attempt_selftest():
        technical.append("the one-attempt registry admitted a second attempt on one root")
    doc = json.loads(committed)
    for value, why in ((doc["evaluator"]["pair_bound"], "w (pair bound): D1-scoring"),
                       (doc["formal"]["root_commitment_sha256"], "the formal root commitment: generated by the operator "
                                                                 "at freeze, D4"),
                       (doc["formal"]["environment_manifest_sha256"], "the environment manifest: measured on the "
                                                                      "approved machine, D7"),
                       (doc["formal"].get("candidate"), "the candidate (or NONE for a baseline-only attempt): D4")):
        if value == v03p.ODR:
            owner.append(f"{why} is OWNER_DECISION_REQUIRED")
    if doc.get("status") != "FROZEN":
        owner.append(f"identity status is {doc.get('status')!r}: freezing is the owner's act (D4, OD-19)")
    path = approvals_path or APPROVALS_PATH
    record = json.loads(path.read_bytes()) if path.is_file() else {}
    record = record if isinstance(record, Mapping) else {}
    for decision in REQUIRED_APPROVALS:
        entry = record.get(decision)
        ok = (isinstance(entry, Mapping) and entry.get("status") == "APPROVED" and bool(entry.get("choice"))
              and entry.get("prereg_sha256") == prereg_sha)
        if ok and decision == "D1-scoring":
            ok = entry.get("pair_bound") == doc["evaluator"]["pair_bound"] != v03p.ODR
        if ok and decision == "OD-3":
            ok = bool(head) and entry.get("certified_head") == head
        if not ok:
            owner.append(f"owner decision {decision} is not APPROVED for this preregistration ({prereg_sha[:12]}...) "
                         f"in {path.name}")
    status = BLOCKED if technical else PENDING_OWNER if owner else PASS
    return {"status": status, "technical_blockers": technical, "owner_and_certification": owner,
            "agreement_cases": len(cases), "evidence_tests": len(tests), "head": head, "prereg_sha256": prereg_sha,
            "ledger": {k: [v[0], list(v[1]), v[2]] for k, v in sorted(rows.items())},
            "pair_bound": v03e.PAIR_BOUND if not isinstance(v03e.PAIR_BOUND, v03e.PairBound) else v03e.PAIR_BOUND.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 freeze-readiness gate (read-only)")
    parser.add_argument("--approvals", type=pathlib.Path, default=None, help="the owner's approval record")
    args = parser.parse_args(argv)
    result = check(args.approvals, evidence=collect_evidence())
    sys.stdout.write(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return 0 if result["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
