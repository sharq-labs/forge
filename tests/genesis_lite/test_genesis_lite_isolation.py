"""OD-20 hardening: a hostile proposer must not reach hidden worlds or the operator's secrets.

In-process (the v0 pilot's mode) two attacks steal the hidden law: a heap scan for HiddenWorld objects and a stack walk
to the operator's master seed, which re-derives every world. With ``isolation="proposer_process"`` the arm runs in a
fresh interpreter that never holds either, and the same attacks find nothing. This is a same-account PROCESS
separation, not a proven security boundary: the escrow keeps saying SECURITY_BOUNDARY_NOT_PROVEN.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from benchmarks.genesis_lite import arms, harness
from tests.genesis_lite import attack_arms

MASTER = bytes(range(32))
LAW_KINDS = ("discoverable", "spurious_correlate", "confounded")


def _run(name: str, isolation: str, presentation: str = "renamed"):
    return harness.run_one(name, getattr(attack_arms, name, None) or arms.ARMS[name][0], master_seed=MASTER,
                           campaign_id="gl-iso-0", presentation=presentation, isolation=isolation,
                           arm_spec=f"tests.genesis_lite.attack_arms:{name}" if hasattr(attack_arms, name) else name)


@pytest.mark.parametrize("attack", ["peek_memory", "walk_frames"])
def test_in_process_the_attack_steals_the_hidden_law(attack):
    rec = _run(attack, "in_process")
    assert rec.status == "VALID"                        # nothing in the run notices: that is why in_process is not admissible
    assert {u["outcome"] for u in rec.universes if u["kind"] in LAW_KINDS} == {"law_pass"}


@pytest.mark.parametrize("attack", ["peek_memory", "walk_frames"])
def test_in_a_proposer_process_the_same_attack_finds_nothing(attack):
    rec = _run(attack, "proposer_process")
    assert rec.status == "VALID" and rec.isolation == "proposer_process"
    assert all(u["answer"] == "no_law" for u in rec.universes)
    assert rec.security_boundary == "SECURITY_BOUNDARY_NOT_PROVEN"


def test_the_proposer_process_gets_no_secret_in_its_environment_or_working_directory(monkeypatch):
    monkeypatch.setenv("FORGE_MASTER_SEED_FOR_TEST", "deadbeef")
    seen = []
    real = harness.ProposerHost.propose

    def capture(self, spec, card, seed, client):
        out = real(self, spec, card, seed, client)
        seen.append(out)
        return out

    monkeypatch.setattr(harness.ProposerHost, "propose", capture)
    rec = _run("scan_environment", "proposer_process")
    assert rec.status == "VALID" and seen
    for proposal in seen:
        found = json.loads(proposal["rationale"])
        assert found["env"] == [] and found["cwd_files"] == []


def test_the_proposer_process_cannot_read_the_operators_memory_where_the_kernel_forbids_it(monkeypatch):
    seen = []
    real = harness.ProposerHost.propose
    monkeypatch.setattr(harness.ProposerHost, "propose",
                        lambda self, spec, card, seed, client: seen.append(real(self, spec, card, seed, client)) or seen[-1])
    rec = _run("read_parent_memory", "proposer_process")
    assert rec.status == "VALID" and seen
    outcomes = {p["rationale"] for p in seen}
    scope = pathlib.Path("/proc/sys/kernel/yama/ptrace_scope")
    if os.name == "posix" and scope.exists() and int(scope.read_text().strip() or 0) >= 1:
        assert all(o.startswith("refused") for o in outcomes), outcomes      # Linux YAMA: a child cannot ptrace its parent
    else:
        assert rec.security_boundary == "SECURITY_BOUNDARY_NOT_PROVEN"      # elsewhere this is NOT established


def test_positive_control_isolation_does_not_change_an_honest_arms_outcomes():
    a = _run("careful", "in_process")
    b = _run("careful", "proposer_process")
    assert a.status == b.status == "VALID"
    assert [(u["kind"], u["outcome"]) for u in a.universes] == [(u["kind"], u["outcome"]) for u in b.universes]
    assert b.host_start_seconds > 0


def test_an_unknown_isolation_is_an_invalid_run():
    rec = harness.run_one("careful", arms.ARMS["careful"][0], master_seed=MASTER, campaign_id="gl-iso-1",
                          presentation="anonymous", isolation="none")
    assert rec.status == "INVALID_BENCHMARK"
