"""Choose where the heavy CI jobs run: GitHub-hosted, or the owner's self-hosted PC.

    python -m tools.ci.select_heavy_runner [--check-online]

The result is written to ``$GITHUB_OUTPUT`` as ``heavy_runs_on`` (a JSON array a
job feeds to ``runs-on: ${{ fromJSON(...) }}``) and ``heavy_runner_mode``.

WHAT THIS DECIDES, AND WHAT IT DOES NOT
---------------------------------------
This is a *routing* decision, not a security boundary. A pull request from a
fork runs the workflow file of the fork's own merge commit, so a fork can rewrite
this very step (or the ``runs-on`` line) to name the self-hosted labels itself.
The boundaries that hold are outside the repository's control:

* the machine owner's runner hook (``tools/ci/runner_guard.py``, installed
  root-owned on the PC), which refuses any job whose event payload is not a
  same-repository push / dispatch / pull request from a collaborator; and
* the repository's "require approval for all outside collaborators" setting.

Routing untrusted events to GitHub-hosted runners here keeps their test coverage
without ever offering them the PC.

WHY THE DEFAULT IS ``github-hosted``
------------------------------------
``FORGE_HEAVY_RUNNER`` is a repository variable only an administrator can set.
Unset means GitHub-hosted, so the very change that introduces this file runs
before any runner exists. ``self-hosted`` opts in; any other value is a
configuration error and fails closed rather than silently picking a runner.

WHEN THE PC IS OFF
------------------
With ``self-hosted`` selected, a job whose runner is offline waits in GitHub's
queue -- it is never re-routed. The required checks stay pending, not green. With
the optional ``RUNNER_STATUS_TOKEN`` secret (read-only, Administration: read)
and ``--check-online``, the run fails immediately with an actionable message
instead. Neither path bypasses the runner.

With the same token, selecting the PC also REQUIRES the repository's fork-approval
setting to be ``all_external_contributors``: the machine-side guard only holds while
no admitted job is hostile, so the setting that keeps strangers' workflows from
running at all is a precondition, not advice. Without the token this cannot be
checked and the run says so. The token is visible to same-repository pull-request
code in the step that uses it (as any repository secret is); grant it read access only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

MODE_HOSTED = "github-hosted"
MODE_SELF_HOSTED = "self-hosted"
HOSTED_LABELS: tuple[str, ...] = ("ubuntu-latest",)
SELF_HOSTED_LABELS: tuple[str, ...] = ("self-hosted", "linux", "x64", "forge-pc")

#: Events whose triggering identity must hold write access to the repository.
WRITER_EVENTS = frozenset({"push", "workflow_dispatch"})
#: A same-repository pull request author is one of these on a repository they can push to.
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


class SelectionError(RuntimeError):
    """The selection could not be made safely; the job must fail, not guess."""


@dataclass(frozen=True)
class Decision:
    mode: str
    labels: tuple[str, ...]
    reason: str

    @property
    def runs_on_json(self) -> str:
        return json.dumps(list(self.labels))


def normalize_request(value: str | None) -> str:
    """``FORGE_HEAVY_RUNNER``: empty means the default, unknown is an error."""
    text = (value or "").strip().lower()
    if text in ("", MODE_HOSTED):
        return MODE_HOSTED
    if text == MODE_SELF_HOSTED:
        return MODE_SELF_HOSTED
    raise SelectionError(
        f"FORGE_HEAVY_RUNNER={value!r} is not one of {MODE_HOSTED!r} (default) or "
        f"{MODE_SELF_HOSTED!r}; refusing to guess where the heavy jobs should run"
    )


def _same_repository(head: str, repository: str) -> bool:
    return bool(head) and bool(repository) and head.lower() == repository.lower()


def untrusted_reason(
    *,
    event: str,
    repository: str,
    head_repository: str,
    head_is_fork: str,
    author_association: str,
) -> str | None:
    """Why this event may not use the personal runner, or ``None`` if it may."""
    if event in WRITER_EVENTS:
        return None
    if event != "pull_request":
        return f"event {event!r} is not one the personal runner accepts"
    if not _same_repository(head_repository, repository):
        return (
            f"pull request head repository {head_repository or '<unknown>'!r} is not "
            f"{repository!r}"
        )
    if str(head_is_fork).strip().lower() != "false":
        return "pull request head repository is a fork (or its fork status is unknown)"
    if (author_association or "").strip().upper() not in TRUSTED_ASSOCIATIONS:
        return (
            f"pull request author association {author_association or '<unknown>'!r} "
            f"is not one of {sorted(TRUSTED_ASSOCIATIONS)}"
        )
    return None


def decide(
    *,
    requested: str | None,
    event: str,
    repository: str,
    head_repository: str = "",
    head_is_fork: str = "",
    author_association: str = "",
) -> Decision:
    mode = normalize_request(requested)
    if mode == MODE_HOSTED:
        return Decision(MODE_HOSTED, HOSTED_LABELS, "FORGE_HEAVY_RUNNER is unset or github-hosted")
    reason = untrusted_reason(
        event=event,
        repository=repository,
        head_repository=head_repository,
        head_is_fork=head_is_fork,
        author_association=author_association,
    )
    if reason is not None:
        return Decision(
            MODE_HOSTED,
            HOSTED_LABELS,
            f"untrusted for the personal runner ({reason}); running on GitHub-hosted",
        )
    return Decision(MODE_SELF_HOSTED, SELF_HOSTED_LABELS, "trusted same-repository event")


def runner_online(payload: Mapping[str, Any], labels: Sequence[str]) -> list[str]:
    """Names of online runners carrying every label (case-insensitive)."""
    wanted = {label.lower() for label in labels}
    names = []
    for runner in payload.get("runners", ()):
        have = {str(item.get("name", "")).lower() for item in runner.get("labels", ())}
        if runner.get("status") == "online" and wanted <= have:
            names.append(str(runner.get("name", "")))
    return sorted(names)


def fetch_runners(repository: str, token: str) -> Mapping[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/runners?per_page=100",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SelectionError(f"could not read the runner list to check availability: {exc}") from exc


STRICT_APPROVAL = "all_external_contributors"


def fetch_fork_approval(repository: str, token: str) -> str:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/permissions/fork-pr-contributor-approval",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
            return str(json.load(response).get("approval_policy", ""))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SelectionError(f"could not read the fork-approval setting: {exc}") from exc


def require_strict_approval(policy: str) -> None:
    if policy != STRICT_APPROVAL:
        raise SelectionError(
            f"the repository's fork-pull-request approval policy is {policy or '<unreadable>'!r}, not "
            f"{STRICT_APPROVAL!r}. Selecting the personal runner requires every outside contributor's workflow "
            "run to be approved first (Settings > Actions > General, or the command in "
            "docs/assurance/SELF_HOSTED_RUNNER.md section 6). Jobs are NOT re-routed automatically."
        )


def _write_output(path: str | None, decision: Decision) -> None:
    if not path:
        return
    with open(path, "ab") as handle:
        handle.write(f"heavy_runs_on={decision.runs_on_json}\n".encode("utf-8"))
        handle.write(f"heavy_runner_mode={decision.mode}\n".encode("utf-8"))


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--check-online", action="store_true",
                        help="fail now if the self-hosted runner is offline (needs RUNNER_STATUS_TOKEN)")
    args = parser.parse_args(argv)
    try:
        decision = decide(
            requested=env.get("FORGE_HEAVY_RUNNER"),
            event=env.get("GITHUB_EVENT_NAME", ""),
            repository=env.get("GITHUB_REPOSITORY", ""),
            head_repository=env.get("HEAD_REPOSITORY", ""),
            head_is_fork=env.get("HEAD_IS_FORK", ""),
            author_association=env.get("AUTHOR_ASSOCIATION", ""),
        )
        print(f"heavy jobs: {decision.mode} {decision.runs_on_json} -- {decision.reason}")
        if decision.mode == MODE_SELF_HOSTED:
            token = env.get("RUNNER_STATUS_TOKEN", "")
            if args.check_online and token:
                online = runner_online(fetch_runners(env.get("GITHUB_REPOSITORY", ""), token),
                                       decision.labels)
                if not online:
                    raise SelectionError(
                        f"no online runner carries {list(decision.labels)}. The PC is off or its "
                        "runner service is stopped. Start it, or set the repository variable "
                        f"FORGE_HEAVY_RUNNER to {MODE_HOSTED!r} to run on GitHub-hosted runners. "
                        "Jobs are NOT re-routed automatically."
                    )
                print(f"online runner(s): {online}")
                require_strict_approval(fetch_fork_approval(env.get("GITHUB_REPOSITORY", ""), token))
                print(f"fork approval policy: {STRICT_APPROVAL}")
            else:
                print("::notice::heavy jobs target the self-hosted runner; availability and the fork-approval "
                      "setting were NOT checked (no RUNNER_STATUS_TOKEN), so jobs wait in the queue until a "
                      "forge-pc runner is online")
    except SelectionError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    _write_output(env.get("GITHUB_OUTPUT"), decision)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
