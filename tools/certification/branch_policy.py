"""Local assurance merge governance, inspected through read-only GitHub policy APIs.

GitHub does not attest test execution. Scientific assurance is produced locally
and bound to the exact commit by the local assurance receipt. Required GitHub
status checks are NONE. PR review, merge-only lineage and protection from force
pushes/deletion remain required; unreadable settings remain unverified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any, Mapping, Sequence

REQUIRED_STATUS_CHECKS: tuple[str, ...] = ()
GITHUB_ACTIONS_APP_ID = 15368

POLICY = {
    "target": "the default branch (main)",
    "mechanism": "a repository ruleset (readable by CI) rather than classic branch protection",
    "enforcement": "active",
    "bypass_actors": "none -- not repository admins, not maintainers",
    "rules": {
        "pull_request": {
            "required_approving_review_count": ">= 1",
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": "recommended, with CODEOWNERS covering the certification_control area",
            "require_last_push_approval": "recommended: human review of certification-control changes",
            "allowed_merge_methods": ["merge"],
        },
        "required_status_checks": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [
                {"context": name, "integration_id": GITHUB_ACTIONS_APP_ID}
                for name in REQUIRED_STATUS_CHECKS
            ],
        },
        "non_fast_forward": "enabled (blocks force pushes)",
        "deletion": "enabled (blocks branch deletion)",
    },
}


def policy_problems(
    rules: Sequence[Mapping[str, Any]],
    branch: Mapping[str, Any],
    repository: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    """``(problems, unverified)`` for the policy against what GitHub reports."""
    problems: list[str] = []
    unverified: list[str] = []
    by_type: dict[str, list[Mapping[str, Any]]] = {}
    for rule in rules:
        by_type.setdefault(str(rule.get("type")), []).append(rule)

    classic = branch.get("protection") or {}
    classic_enabled = bool(classic.get("enabled"))
    classic_checks = set((classic.get("required_status_checks") or {}).get("contexts") or ())
    classic_level = (classic.get("required_status_checks") or {}).get("enforcement_level")

    if "pull_request" not in by_type:
        if classic_enabled:
            unverified.append("pull requests before merging: classic protection does not expose this to a read token")
        else:
            problems.append("pull requests are not required before merging")

    contexts = set(classic_checks) if classic_enabled and classic_level in ("everyone", "non_admins") else set()
    for rule in by_type.get("required_status_checks", []):
        parameters = rule.get("parameters") or {}
        contexts |= {str(c.get("context")) for c in parameters.get("required_status_checks") or ()}
    if contexts:
        problems.append(f"GitHub required status checks must be NONE for local-only assurance; found {sorted(contexts)}")

    for kind, meaning in (("non_fast_forward", "force pushes"), ("deletion", "branch deletion")):
        if kind not in by_type:
            if classic_enabled:
                unverified.append(f"blocking {meaning}: classic protection does not expose this to a read token")
            else:
                problems.append(f"{meaning}: not blocked")

    methods: set[str] | None = None
    for rule in by_type.get("pull_request", []):
        allowed = (rule.get("parameters") or {}).get("allowed_merge_methods")
        if allowed:
            methods = set(allowed) if methods is None else methods & set(allowed)
    if methods is None:
        flags = {
            "merge": repository.get("allow_merge_commit"),
            "squash": repository.get("allow_squash_merge"),
            "rebase": repository.get("allow_rebase_merge"),
        }
        if any(flag is None for flag in flags.values()):
            # GitHub omits these for tokens without push access to settings.
            unverified.append(
                "merge methods: not restricted by a ruleset, and the repository "
                "settings are not readable with this token"
            )
            methods = {"merge"}
        else:
            methods = {name for name, flag in flags.items() if flag}
    if methods - {"merge"}:
        problems.append(
            f"merge methods {sorted(methods - {'merge'})} are allowed; they rewrite "
            f"the verified certificate child and break certificate lineage"
        )
    if "merge" not in methods:
        problems.append("merge commits are not allowed, so no certified pull request can merge")

    unverified.append("bypass actors: not readable without administration permission")
    return problems, unverified


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--print-policy", action="store_true")
    args = parser.parse_args(argv)
    if args.print_policy:
        print(json.dumps(POLICY, indent=2))
        return 0

    def gh(path: str) -> Any:
        done = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(f"gh api {path} failed: {done.stderr.strip()}")
        return json.loads(done.stdout)

    rules = gh(f"repos/{args.repository}/rules/branches/{args.branch}")
    branch = gh(f"repos/{args.repository}/branches/{args.branch}")
    repository = gh(f"repos/{args.repository}")
    problems, unverified = policy_problems(rules, branch, repository)
    for problem in problems:
        print(f"POLICY NOT ENFORCED: {problem}")
    for item in unverified:
        print(f"unverified: {item}")
    if problems:
        print("Required configuration (docs/assurance/BRANCH_PROTECTION.md):")
        print(json.dumps(POLICY, indent=2))
    print("FAILED" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
