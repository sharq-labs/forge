"""The self-hosted runner's routing decision and the owner's admission guard.

Neither is a proof that same-repository code is safe to run. What is pinned here is
that an UNTRUSTED event -- a fork, a stranger, an unusual event type, a payload that
cannot be read -- is never routed to, and never admitted by, the personal runner, and
that no configuration mistake silently picks a runner.
"""

from __future__ import annotations

import json

import pytest

from tools.ci import runner_guard as guard
from tools.ci import select_heavy_runner as sel

REPO = "sharq-labs/forge"
WORKFLOWS = ("tests", "recertify-hardened-core", "trust-mutations", "self-hosted-smoke")


def _decide(**overrides):
    fields = dict(
        requested="self-hosted", event="pull_request", repository=REPO,
        head_repository=REPO, head_is_fork="false", author_association="COLLABORATOR",
    )
    fields.update(overrides)
    return sel.decide(**fields)


# ---------------------------------------------------------------- routing
@pytest.mark.parametrize("requested", [None, "", "  ", "github-hosted", "GitHub-Hosted"])
def test_the_default_is_github_hosted_so_the_change_that_adds_this_runs_before_any_runner_exists(requested):
    decision = _decide(requested=requested)
    assert decision.mode == sel.MODE_HOSTED
    assert decision.labels == sel.HOSTED_LABELS


@pytest.mark.parametrize("requested", ["self_hosted", "selfhosted", "true", "forge-pc", "ubuntu-latest"])
def test_an_unknown_request_is_an_error_not_a_guess(requested):
    with pytest.raises(sel.SelectionError, match="refusing to guess"):
        _decide(requested=requested)


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_a_writer_event_uses_the_personal_runner_when_it_is_selected(event):
    decision = _decide(event=event, head_repository="", head_is_fork="", author_association="")
    assert decision.mode == sel.MODE_SELF_HOSTED
    assert decision.labels == sel.SELF_HOSTED_LABELS


def test_a_same_repository_pull_request_by_a_collaborator_uses_it():
    assert _decide().mode == sel.MODE_SELF_HOSTED


@pytest.mark.parametrize(
    "overrides,why",
    [
        (dict(head_repository="someone/forge"), "not"),
        (dict(head_repository="sharq-labs/forge-evil"), "not"),
        (dict(head_repository=""), "unknown"),
        (dict(head_is_fork="true"), "fork"),
        (dict(head_is_fork=""), "fork"),
        (dict(author_association="NONE"), "association"),
        (dict(author_association="FIRST_TIME_CONTRIBUTOR"), "association"),
        (dict(author_association="CONTRIBUTOR"), "association"),
        (dict(author_association=""), "association"),
        (dict(event="pull_request_target"), "not one the personal runner accepts"),
        (dict(event="issue_comment"), "not one the personal runner accepts"),
        (dict(event="schedule"), "not one the personal runner accepts"),
        (dict(event=""), "not one the personal runner accepts"),
    ],
)
def test_an_untrusted_event_is_kept_on_github_hosted_runners(overrides, why):
    decision = _decide(**overrides)
    assert decision.mode == sel.MODE_HOSTED
    assert decision.labels == sel.HOSTED_LABELS
    assert why in decision.reason


def test_repository_comparison_is_case_insensitive_but_exact():
    assert _decide(head_repository="SHARQ-labs/Forge").mode == sel.MODE_SELF_HOSTED
    assert _decide(head_repository="sharq-labs/forge ").mode == sel.MODE_HOSTED


def test_runs_on_is_a_json_array_a_job_can_feed_to_fromjson():
    assert json.loads(_decide().runs_on_json) == ["self-hosted", "linux", "x64", "forge-pc"]
    assert json.loads(_decide(requested=None).runs_on_json) == ["ubuntu-latest"]


def _env(tmp_path, **extra):
    out = tmp_path / "output"
    out.write_bytes(b"")
    env = {
        "FORGE_HEAVY_RUNNER": "self-hosted", "GITHUB_EVENT_NAME": "push",
        "GITHUB_REPOSITORY": REPO, "GITHUB_OUTPUT": str(out),
    }
    env.update(extra)
    return env, out


def test_the_cli_writes_the_outputs_the_workflow_reads(tmp_path):
    env, out = _env(tmp_path)
    assert sel.main([], env) == 0
    text = out.read_text(encoding="utf-8")
    assert 'heavy_runs_on=["self-hosted", "linux", "x64", "forge-pc"]' in text
    assert "heavy_runner_mode=self-hosted" in text


def test_a_misconfigured_variable_fails_the_job_and_writes_no_output(tmp_path):
    env, out = _env(tmp_path, FORGE_HEAVY_RUNNER="selfhosted")
    assert sel.main([], env) == 1
    assert out.read_bytes() == b""


# ------------------------------------------------- an offline PC is a clear failure, never a re-route
def _runner(name, status, *labels):
    return {"name": name, "status": status, "labels": [{"name": label} for label in labels]}


LABELS = ("self-hosted", "linux", "x64", "forge-pc")


def test_only_an_online_runner_with_every_label_counts():
    payload = {"runners": [
        _runner("a", "offline", "self-hosted", "Linux", "X64", "forge-pc"),
        _runner("b", "online", "self-hosted", "Linux", "X64"),
        _runner("c", "online", "self-hosted", "Linux", "X64", "forge-pc"),
    ]}
    assert sel.runner_online(payload, LABELS) == ["c"]
    assert sel.runner_online({"runners": []}, LABELS) == []
    assert sel.runner_online({}, LABELS) == []


def test_an_offline_pc_fails_with_the_way_out_and_does_not_reroute(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sel, "fetch_runners", lambda repository, token: {"runners": []})
    env, out = _env(tmp_path, RUNNER_STATUS_TOKEN="t")
    assert sel.main(["--check-online"], env) == 1
    err = capsys.readouterr().err
    assert "FORGE_HEAVY_RUNNER" in err and "NOT re-routed" in err
    assert out.read_bytes() == b""


def test_an_online_pc_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(sel, "fetch_runners", lambda repository, token: {
        "runners": [_runner("forge-pc-1", "online", "self-hosted", "Linux", "X64", "forge-pc")]})
    env, out = _env(tmp_path, RUNNER_STATUS_TOKEN="t")
    assert sel.main(["--check-online"], env) == 0
    assert "heavy_runner_mode=self-hosted" in out.read_text(encoding="utf-8")


def test_without_a_status_token_the_job_waits_in_the_queue_and_says_so(tmp_path, capsys):
    env, _ = _env(tmp_path)
    assert sel.main(["--check-online"], env) == 0
    assert "wait in the queue" in capsys.readouterr().out


def test_an_unreadable_runner_list_fails_rather_than_assuming_online(tmp_path, monkeypatch):
    def boom(repository, token):
        raise sel.SelectionError("could not read the runner list")
    monkeypatch.setattr(sel, "fetch_runners", boom)
    env, out = _env(tmp_path, RUNNER_STATUS_TOKEN="t")
    assert sel.main(["--check-online"], env) == 1
    assert out.read_bytes() == b""


def test_hosted_selection_never_touches_the_runner_api(tmp_path, monkeypatch):
    def forbidden(repository, token):  # pragma: no cover - must not run
        raise AssertionError("the API was called")
    monkeypatch.setattr(sel, "fetch_runners", forbidden)
    env, _ = _env(tmp_path, FORGE_HEAVY_RUNNER="", RUNNER_STATUS_TOKEN="t")
    assert sel.main(["--check-online"], env) == 0


# ------------------------------------------------------------------ the machine-side guard
def _pull_payload(**overrides):
    pull = {
        "head": {"repo": {"full_name": REPO, "fork": False}},
        "base": {"repo": {"full_name": REPO}},
        "author_association": "COLLABORATOR",
    }
    pull.update(overrides)
    return {"pull_request": pull}


def _job_env(event="pull_request", workflow="tests", ref="refs/pull/7/merge", **extra):
    env = {
        "GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": event,
        "GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/{workflow}.yml@{ref}",
        "GITHUB_REF": ref, "GITHUB_EVENT_PATH": "/event.json",
    }
    env.update(extra)
    return env


def _evaluate(env, payload=None):
    return guard.evaluate(env, repository=REPO, workflows=WORKFLOWS, load_event=lambda path: payload)


def test_the_guard_admits_a_same_repository_collaborator_pull_request():
    admitted, reason = _evaluate(_job_env(), _pull_payload())
    assert admitted, reason


@pytest.mark.parametrize("event,ref", [("push", "refs/heads/main"), ("workflow_dispatch", "refs/heads/feature")])
def test_the_guard_admits_a_branch_push_or_dispatch(event, ref):
    admitted, reason = _evaluate(_job_env(event=event, ref=ref))
    assert admitted, reason


@pytest.mark.parametrize(
    "mutate,payload",
    [
        (dict(), _pull_payload(head={"repo": {"full_name": "attacker/forge", "fork": True}})),
        (dict(), _pull_payload(head={"repo": {"full_name": REPO, "fork": True}})),
        (dict(), _pull_payload(head={"repo": {"full_name": REPO}})),          # fork status unknown
        (dict(), _pull_payload(head={"repo": None})),                          # a deleted fork
        (dict(), _pull_payload(head={})),
        (dict(), _pull_payload(base={"repo": {"full_name": "attacker/forge"}})),
        (dict(), _pull_payload(author_association="NONE")),
        (dict(), _pull_payload(author_association="FIRST_TIME_CONTRIBUTOR")),
        (dict(), _pull_payload(author_association="CONTRIBUTOR")),
        (dict(), {"pull_request": "not-an-object"}),
        (dict(), {}),
        (dict(), None),                                                        # unreadable payload
        (dict(GITHUB_EVENT_PATH=""), _pull_payload()),                         # no payload path at all
        (dict(GITHUB_REPOSITORY="sharq-labs/forge-evil"), _pull_payload()),
        (dict(GITHUB_EVENT_NAME="pull_request_target"), _pull_payload()),
        (dict(GITHUB_EVENT_NAME="issue_comment"), _pull_payload()),
        (dict(GITHUB_EVENT_NAME="schedule"), _pull_payload()),
        (dict(GITHUB_EVENT_NAME=""), _pull_payload()),
    ],
)
def test_the_guard_refuses_everything_it_cannot_positively_verify(mutate, payload):
    admitted, reason = _evaluate(_job_env(**mutate), payload)
    assert not admitted, reason


@pytest.mark.parametrize(
    "workflow_ref",
    [
        "",
        f"{REPO}/.github/workflows/pwn.yml@refs/pull/7/merge",
        f"{REPO}/.github/workflows/tests.yml.evil@refs/pull/7/merge",
        f"{REPO}/.github/workflows/../tests.yml@refs/pull/7/merge",
        f"{REPO}/.github/workflows/nested/tests.yml@refs/pull/7/merge",
        f"attacker/forge/.github/workflows/tests.yml@refs/pull/7/merge",
        f"{REPO}-evil/.github/workflows/tests.yml@refs/pull/7/merge",
        f"{REPO}/.github/workflows/tests.yml@main",
    ],
)
def test_the_guard_refuses_a_workflow_that_is_not_on_the_allow_list(workflow_ref):
    env = _job_env()
    env["GITHUB_WORKFLOW_REF"] = workflow_ref
    admitted, _ = _evaluate(env, _pull_payload())
    assert not admitted


@pytest.mark.parametrize("ref", ["refs/tags/v1", "refs/pull/7/merge", "main", ""])
def test_a_push_must_be_to_a_branch(ref):
    admitted, _ = _evaluate(_job_env(event="push", ref=ref))
    assert not admitted


def test_an_unconfigured_guard_refuses():
    assert not guard.evaluate(_job_env(), repository="", workflows=WORKFLOWS, load_event=lambda p: _pull_payload())[0]
    assert not guard.evaluate(_job_env(), repository=REPO, workflows=(), load_event=lambda p: _pull_payload())[0]


def test_the_guard_reads_a_real_payload_file_and_exit_codes_match(tmp_path, capsys):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_pull_payload()), encoding="utf-8")
    bad.write_text(json.dumps(_pull_payload(author_association="NONE")), encoding="utf-8")
    argv = ["--repository", REPO, "--workflows", ",".join(WORKFLOWS)]
    assert guard.main(argv, _job_env(GITHUB_EVENT_PATH=str(good))) == 0
    assert guard.main(argv, _job_env(GITHUB_EVENT_PATH=str(bad))) == 1
    assert guard.main(argv, _job_env(GITHUB_EVENT_PATH=str(tmp_path / "missing.json"))) == 1
    assert "REFUSED" in capsys.readouterr().err


def test_routing_and_guard_agree_on_who_is_trusted():
    """The workflow-side routing must never be MORE permissive than the machine-side guard."""
    for association in ("OWNER", "MEMBER", "COLLABORATOR", "CONTRIBUTOR", "NONE", "FIRST_TIME_CONTRIBUTOR", ""):
        for fork in (True, False, None):
            routed = _decide(author_association=association, head_is_fork="" if fork is None else str(fork).lower())
            payload = _pull_payload(author_association=association)
            payload["pull_request"]["head"]["repo"] = (
                {"full_name": REPO} if fork is None else {"full_name": REPO, "fork": fork}
            )
            admitted, _ = _evaluate(_job_env(), payload)
            if routed.mode == sel.MODE_SELF_HOSTED:
                assert admitted, (association, fork)
