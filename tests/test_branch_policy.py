"""The merge policy the certificate checks depend on is stated exactly and detected honestly.

Finding G. Repository files cannot protect ``main``. What they can do is say
exactly what must be configured and recognise, from what GitHub reports to a
read-only token, whether it is. These cases are the responses GitHub returns
for the configurations that matter, including the unprotected one ``main`` had.
"""

from __future__ import annotations

from tools.certification.branch_policy import (
    GITHUB_ACTIONS_APP_ID,
    POLICY,
    REQUIRED_STATUS_CHECKS,
    policy_problems,
)

UNPROTECTED_BRANCH = {"protected": False, "protection": {
    "enabled": False, "required_status_checks": {"checks": [], "contexts": [], "enforcement_level": "off"}}}
MERGE_ONLY = {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False}


def _ruleset(*, contexts=REQUIRED_STATUS_CHECKS, strict=True, methods=("merge",), omit=()):
    rules = [
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": 1, "allowed_merge_methods": list(methods)}},
        {"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": strict,
            "required_status_checks": [{"context": c, "integration_id": GITHUB_ACTIONS_APP_ID} for c in contexts]}},
        {"type": "non_fast_forward"},
        {"type": "deletion"},
    ]
    return [rule for rule in rules if rule["type"] not in omit]


def test_the_state_main_was_in_is_reported_as_unprotected():
    problems, _ = policy_problems([], UNPROTECTED_BRANCH, {"allow_merge_commit": True,
                                                         "allow_squash_merge": True, "allow_rebase_merge": True})
    text = "\n".join(problems)
    for fragment in ("pull requests are not required", "no status checks are required",
                     "force pushes", "branch deletion", "squash"):
        assert fragment in text, fragment


def test_the_required_ruleset_satisfies_the_policy():
    problems, unverified = policy_problems(_ruleset(), UNPROTECTED_BRANCH, MERGE_ONLY)
    assert problems == []
    assert any("bypass" in item for item in unverified), "bypass actors are never assumed"


def test_requiring_only_the_conditional_child_jobs_is_not_enough():
    """``verify_certificate_child`` is SKIPPED on a source commit, and skipped passes."""
    rules = _ruleset(contexts=("verify_certificate_child", "certificate-child"))
    problems, _ = policy_problems(rules, UNPROTECTED_BRANCH, MERGE_ONLY)
    assert any("recertification-gate" in p and "tests-gate" in p for p in problems)


def test_a_branch_that_need_not_be_up_to_date_fails():
    problems, _ = policy_problems(_ruleset(strict=False), UNPROTECTED_BRANCH, MERGE_ONLY)
    assert any("up to date" in p for p in problems)


def test_squash_or_rebase_merges_break_lineage():
    problems, _ = policy_problems(_ruleset(methods=("merge", "squash")), UNPROTECTED_BRANCH, MERGE_ONLY)
    assert any("squash" in p for p in problems)
    unrestricted = [r for r in _ruleset() if r["type"] != "pull_request"] + [{"type": "pull_request", "parameters": {}}]
    problems, _ = policy_problems(unrestricted, UNPROTECTED_BRANCH, {**MERGE_ONLY, "allow_rebase_merge": True})
    assert any("rebase" in p for p in problems)


def test_missing_force_push_or_deletion_rules_fail():
    for omitted in ("non_fast_forward", "deletion"):
        problems, _ = policy_problems(_ruleset(omit=(omitted,)), UNPROTECTED_BRANCH, MERGE_ONLY)
        assert problems, omitted


def test_classic_protection_is_judged_on_what_it_exposes_and_the_rest_is_unverified():
    branch = {"protected": True, "protection": {"enabled": True, "required_status_checks": {
        "contexts": list(REQUIRED_STATUS_CHECKS), "enforcement_level": "non_admins"}}}
    problems, unverified = policy_problems([], branch, MERGE_ONLY)
    assert any("administrators" in p for p in problems)
    assert any("force pushes" in item for item in unverified)


def test_unreadable_merge_settings_are_unverified_not_assumed():
    rules = [r for r in _ruleset() if r["type"] != "pull_request"] + [{"type": "pull_request", "parameters": {}}]
    problems, unverified = policy_problems(rules, UNPROTECTED_BRANCH, {})
    assert problems == []
    assert any("merge methods" in item for item in unverified)


def test_the_stated_policy_names_the_gates():
    contexts = [c["context"] for c in POLICY["rules"]["required_status_checks"]["required_status_checks"]]
    assert contexts == list(REQUIRED_STATUS_CHECKS)
    assert POLICY["rules"]["pull_request"]["allowed_merge_methods"] == ["merge"]
