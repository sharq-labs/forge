"""The merge policy the certificate child's checks depend on, and whether ``main`` enforces it.

    python -m tools.certification.branch_policy --repository OWNER/REPO [--branch main]

WHAT REPOSITORY FILES CANNOT DO
-------------------------------
Every check in the two workflows is advisory until GitHub is told to require
it. On the day this was written ``main`` had no branch protection and no
ruleset, so a pull request could be merged with its recertification red, still
running, or never started. Nothing in this repository can change that; an
administrator has to. What this module can do is state the policy exactly,
and detect -- from CI, with the default token -- whether it is in force.

Two facts shape the policy:

* **A skipped required check passes.** Every job in both workflows is
  conditional on the change's ownership mode, so requiring a job such as
  ``verify_certificate_child`` lets a head through on every path where that job
  is skipped -- including a core source commit whose certify job failed. The
  policy therefore requires the two unconditional aggregate gates,
  ``recertification-gate`` and ``tests-gate``, which know which jobs had to
  succeed for the mode (``tools/certification/recertification_scope.py``).
* **Only merge commits preserve lineage.** A squash or rebase merge writes new
  commits: the certificate on ``main`` would name a commit that is not in
  ``main``'s history, and the certificate child whose lineage and provenance
  were verified would not be what merged.

Readable with the default ``GITHUB_TOKEN``: the active rules for a branch
(``GET /repos/{r}/rules/branches/{b}``, repository rulesets), the branch's
protection summary, and the repository's merge-method settings. NOT readable
without administration permission: ruleset bypass actors and classic
protection's force-push and deletion settings. Anything that cannot be read is
reported as unverified, never assumed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any, Mapping, Sequence

REQUIRED_STATUS_CHECKS = ("recertification-gate", "tests-gate")
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
            "require_last_push_approval": "recommended: the certify job pushes the child after review",
            "allowed_merge_methods": ["merge"],
        },
        "required_status_checks": {
            "strict_required_status_checks_policy": True,
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

    contexts: set[str] = set()
    strict = False
    for rule in by_type.get("required_status_checks", []):
        parameters = rule.get("parameters") or {}
        strict = strict or bool(parameters.get("strict_required_status_checks_policy"))
        contexts |= {str(c.get("context")) for c in parameters.get("required_status_checks") or ()}
    if by_type.get("required_status_checks"):
        missing = sorted(set(REQUIRED_STATUS_CHECKS) - contexts)
        if missing:
            problems.append(f"required status checks do not include {missing}")
        if not strict:
            problems.append("branches are not required to be up to date before merging")
    elif classic_enabled and classic_level in ("everyone", "non_admins"):
        missing = sorted(set(REQUIRED_STATUS_CHECKS) - classic_checks)
        if missing:
            problems.append(f"classic protection does not require {missing}")
        if classic_level != "everyone":
            problems.append("classic protection lets administrators merge without the required checks")
        unverified.append("up-to-date requirement: not exposed by the branch summary")
    else:
        problems.append(f"no status checks are required; {list(REQUIRED_STATUS_CHECKS)} must be")

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
