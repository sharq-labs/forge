"""The owner's admission check for the self-hosted runner. Runs in the job-started hook.

    python3 runner_guard.py --repository OWNER/REPO --workflows tests,recertify-hardened-core

Exit 0 admits the job; exit 1 refuses it before any step of the workflow runs.

WHY THIS LIVES ON THE MACHINE
-----------------------------
For a public repository the only unforgeable place to refuse a job is the runner
itself. A fork's pull request executes the workflow file of *its own* merge
commit, so nothing written in the repository -- ``if:`` conditions, ``runs-on``
expressions, a first step that checks the actor -- can keep a fork off a runner
that the fork's workflow names. This file is installed root-owned and read-only
to the runner user (see docs/assurance/SELF_HOSTED_RUNNER.md); a pull request
that edits the copy in the repository changes nothing on the PC.

WHAT IS ADMITTED
----------------
A job is admitted only if ALL of these hold; anything missing or unreadable is a
refusal, never a pass:

1. it belongs to the configured repository;
2. its event is ``push``, ``workflow_dispatch`` or ``pull_request``;
3. its workflow is one of the named files of that repository;
4. ``push``/``workflow_dispatch``: the ref is a branch of that repository;
   ``pull_request``: the event payload shows base AND head in that repository,
   the head is not a fork, and the author is an OWNER, MEMBER or COLLABORATOR.

This does not make same-repository code safe to run -- a collaborator can still
run arbitrary code here. It removes the untrusted internet from the set of people
who can, and the rest of the design (dedicated WSL distro without Windows drives,
non-root user, no secrets, per-job cleanup) limits what that code can reach.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Callable, Mapping, Sequence

ALLOWED_EVENTS = frozenset({"push", "workflow_dispatch", "pull_request"})
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def _load_event(path: str) -> Mapping[str, Any] | None:
    try:
        with open(path, "rb") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def evaluate(
    env: Mapping[str, str],
    *,
    repository: str,
    workflows: Sequence[str],
    load_event: Callable[[str], Mapping[str, Any] | None] = _load_event,
) -> tuple[bool, str]:
    """``(admitted, reason)`` for one job's environment."""
    if not repository or not workflows:
        return False, "guard is not configured with a repository and a workflow allow-list"
    repo = repository.lower()

    if env.get("GITHUB_REPOSITORY", "").lower() != repo:
        return False, f"repository {env.get('GITHUB_REPOSITORY', '<unset>')!r} is not {repository!r}"

    event = env.get("GITHUB_EVENT_NAME", "")
    if event not in ALLOWED_EVENTS:
        return False, f"event {event or '<unset>'!r} is not admitted"

    ref = env.get("GITHUB_WORKFLOW_REF", "")
    names = "|".join(re.escape(name) for name in workflows)
    if not re.match(rf"^{re.escape(repository)}/\.github/workflows/({names})\.yml@refs/", ref, re.I):
        return False, f"workflow {ref or '<unset>'!r} is not on the allow-list"

    if event in ("push", "workflow_dispatch"):
        git_ref = env.get("GITHUB_REF", "")
        if not git_ref.startswith("refs/heads/"):
            return False, f"{event} ref {git_ref or '<unset>'!r} is not a branch"
        return True, f"{event} on {git_ref}"

    path = env.get("GITHUB_EVENT_PATH", "")
    payload = load_event(path) if path else None
    if payload is None:
        return False, "pull_request event payload is unreadable, so its origin cannot be verified"
    pull = payload.get("pull_request")
    if not isinstance(pull, dict):
        return False, "event payload has no pull_request object"
    head = (pull.get("head") or {}).get("repo") or {}
    base = (pull.get("base") or {}).get("repo") or {}
    if str(head.get("full_name", "")).lower() != repo or str(base.get("full_name", "")).lower() != repo:
        return False, (
            f"pull request head {head.get('full_name', '<unknown>')!r} / base "
            f"{base.get('full_name', '<unknown>')!r} are not both {repository!r}"
        )
    if head.get("fork") is not False:
        return False, "pull request head repository is a fork (or its fork status is unknown)"
    association = str(pull.get("author_association", "")).upper()
    if association not in TRUSTED_ASSOCIATIONS:
        return False, f"pull request author association {association or '<unknown>'!r} is not trusted"
    return True, f"same-repository pull request by a {association}"


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflows", required=True, help="comma-separated workflow file stems")
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    workflows = [name.strip() for name in args.workflows.split(",") if name.strip()]
    admitted, reason = evaluate(env, repository=args.repository, workflows=workflows)
    verdict = "ADMITTED" if admitted else "REFUSED"
    print(f"forge runner guard: {verdict}: {reason}", file=sys.stderr if not admitted else sys.stdout)
    return 0 if admitted else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
