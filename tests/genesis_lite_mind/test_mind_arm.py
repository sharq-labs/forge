"""BR-MIND-01: the Minimal Mind as a Genesis-lite arm, through the unchanged v0.2 harness (escrow, presentation,
separate evaluator, leakage audit, isolated proposer process).

These tests use their own master seeds (never a pilot root) and claim no rate: they check behaviour and boundaries.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib

import pytest

from benchmarks.genesis_lite.harness import code_identity, run_one
from benchmarks.genesis_lite_mind import arm as marm
from engcore.mind.minimal import replay

MASTER = hashlib.sha256(b"BR-MIND-01 test worlds (not a pilot root)").digest()


def _run(presentation, *, arm=marm.mind_full, name="mind_full", isolation="in_process", spec=None, campaign="t-0",
         master=MASTER):
    return run_one(name, arm, master_seed=master, campaign_id=campaign, presentation=presentation, seed=0,
                   isolation=isolation, arm_spec=spec)


def test_the_v0_2_benchmark_identity_is_untouched_by_the_mind():
    _digest, changed = code_identity()
    assert changed == [], f"BR-MIND-01 must not edit a preregistration-pinned file: {changed}"


def test_the_mind_arm_runs_valid_through_the_isolated_proposer_process():
    rec = _run("anonymous", isolation="proposer_process", spec=marm.MIND_ARMS["mind_full"][0])
    assert rec.status == "VALID", rec.reasons
    assert rec.isolation == "proposer_process" and rec.evaluator_status == "VALID"
    assert rec.leakage_audit == "NO_LITERAL_LEAK_FOUND"
    assert all(u["independent_agrees"] for u in rec.universes)


@pytest.mark.parametrize("presentation", ["renamed", "paraphrased", "trap"])
def test_presentation_changes_nothing_the_mind_concludes(presentation):
    """Same hidden worlds, other names / order / wording / textbook vocabulary: the same answers and credits."""
    base = {u["universe_id"]: (u["answer"], u["outcome"], u["credit"]) for u in _run("anonymous").universes}
    other = {u["universe_id"]: (u["answer"], u["outcome"], u["credit"]) for u in _run(presentation).universes}
    assert base == other


class StrictClient:
    """Exposes observe and nothing else; any other attribute access is an attempt to reach past the protocol."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "touched", [])

    def observe(self, universe_id, settings, query_id=""):
        return object.__getattribute__(self, "_inner").observe(universe_id, settings, query_id=query_id)

    def __getattr__(self, name):
        object.__getattribute__(self, "touched").append(name)
        raise AttributeError(f"the Mind reached for {name!r}; a proposer holds observe only")


def test_the_mind_uses_nothing_but_observe_and_cannot_reach_a_hidden_answer():
    seen = []

    def strict_arm(card, client, *, seed=0):
        strict = StrictClient(client)
        out = marm.mind_full(card, strict, seed=seed)
        seen.append(list(strict.touched))
        return out

    rec = _run("anonymous", arm=strict_arm, name="mind_strict")
    assert rec.status == "VALID", rec.reasons
    assert seen and all(t == [] for t in seen)


def test_the_hidden_answer_never_reaches_the_mind_arm_module():
    src = pathlib.Path(marm.__file__).read_bytes().decode()
    for forbidden in ("answer_key", "generate_universe", "HiddenWorld", "master_seed", "ScoreClient", "OperatorClient",
                      "evaluator", "truth_at"):
        assert forbidden not in src, forbidden


def test_exported_traces_pair_with_the_run_and_replay_exactly(tmp_path, monkeypatch):
    folder = tmp_path / marm.TRACE_FOLDER
    folder.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    rec = _run("renamed", campaign="t-trace")
    assert rec.status == "VALID", rec.reasons
    files = sorted(folder.glob("full-0-*.json"))
    assert len(files) == len(rec.universes)
    digests = set(rec.presented_card_digests.values())
    for f in files:
        blob = json.loads(f.read_bytes())
        assert blob["card_digest"] in digests
        problem = marm.problem_from_card(blob["card"])
        assert replay(blob["trace"], problem)["status"] == "VERIFIED"
