"""Roadmap V2 R8: discovery providers own algorithms, FORGE owns authority (PySINDy, BoTorch, Dakota adapters).

Live runs are gated: set FORGE_DISCOVERY_CMD / FORGE_DAKOTA_CMD to a JSON list giving the provider environment's
interpreter (e.g. ``["micromamba", "run", "-n", "discovery", "python", "-I"]``)."""

from __future__ import annotations

import json
import math
import os

import pytest

from engcore.claims.discovery_providers import (
    PROVIDER_STATUS, ProviderRefused, ProviderRun, botorch_suggestion, dakota_output, run_provider, sindy_hypotheses,
)
from engcore.sria.decision import HypothesisKind, HypothesisStatus, ParameterProvenance, ProposerKind

SINDY = ProviderRun("pysindy", "2.1.0", "r" * 64, "q" * 64, {
    "provider": "pysindy", "provider_version": "2.1.0", "terms": ["1", "u", "u^2"], "targets": ["du/dt"],
    "coefficients": [[0.0, -0.50015, 0.0]], "training_score_r2": 0.9999998})


def test_provider_status_never_reads_qualified():
    assert set(PROVIDER_STATUS) == {"pysindy", "botorch", "ax", "dakota", "pysr"}
    assert not any("QUALIFIED" in s.upper().split()[0] for s in PROVIDER_STATUS.values())


def test_sindy_output_becomes_proposed_equations_with_declared_units_only():
    (h,) = sindy_hypotheses(SINDY, units={"u": "m"}, time_unit="s", prefix="sindy-1", condition_ref="cond:decay")
    assert h.kind is HypothesisKind.EQUATION and h.status is HypothesisStatus.PROPOSED and h.proposal.proposer_kind is ProposerKind.ALGORITHM
    assert h.statement_payload["expression"] == {"mul": [{"const": -0.50015}, {"var": "u"}]}
    (p,) = h.parameters
    assert p.provenance is ParameterProvenance.FITTED and p.unit == "(m)/(s)/((m))" and p.source_ref.startswith("provider_run:")
    assert "not evidence" in h.proposal.note
    with pytest.raises(ProviderRefused, match="never defaulted"):
        sindy_hypotheses(SINDY, units={}, time_unit="s", prefix="x", condition_ref="c")


def test_botorch_and_dakota_outputs_carry_no_authority():
    run = ProviderRun("botorch", "0.17.2", "r" * 64, "q" * 64, {"point": [0.56, 0.72], "acquisition": "log_expected_improvement",
                                                                  "acquisition_value": -3.22})
    s = botorch_suggestion(run, names=("x1", "x2"), target_ref="design:beam")
    assert s.point == {"x1": 0.56, "x2": 0.72} and s.acquisition_value == -3.22 and s.engine_id == "botorch"
    d = dakota_output(ProviderRun("dakota", "6.16", "r" * 64, "q" * 64, {"moments": {"mean": 0.02}}))
    assert "untrusted_provider_output" in d and "not evidence" in d["note"]
    with pytest.raises(ProviderRefused, match="unknown runner"):
        run_provider(["python"], "../../etc/passwd", {})


def _cmd(var):
    raw = os.environ.get(var)
    return json.loads(raw) if raw else None


@pytest.mark.skipif(_cmd("FORGE_DISCOVERY_CMD") is None, reason="provider-gated: FORGE_DISCOVERY_CMD not set")
def test_live_pysindy_and_botorch():
    t = [i * 0.1 for i in range(100)]
    run = run_provider(_cmd("FORGE_DISCOVERY_CMD"), "sindy_runner.py",
                       {"t": t, "x": [[2.0 * math.exp(-0.5 * ti)] for ti in t], "feature_names": ["u"], "threshold": 0.05})
    (h,) = sindy_hypotheses(run, units={"u": "m"}, time_unit="s", prefix="live", condition_ref="cond:decay")
    assert abs(h.parameters[0].value + 0.5) < 0.01 and h.status is HypothesisStatus.PROPOSED
    bo = run_provider(_cmd("FORGE_DISCOVERY_CMD"), "botorch_runner.py",
                      {"X": [[0.1, 0.2], [0.5, 0.5], [0.9, 0.1], [0.3, 0.8]], "Y": [0.2, 0.9, 0.4, 0.6], "bounds": [[0, 0], [1, 1]]})
    s = botorch_suggestion(bo, names=("x1", "x2"), target_ref="design:toy")
    assert all(0.0 <= v <= 1.0 for v in s.point.values())


@pytest.mark.skipif(_cmd("FORGE_DAKOTA_CMD") is None, reason="provider-gated: FORGE_DAKOTA_CMD not set")
def test_live_dakota():
    run = run_provider(_cmd("FORGE_DAKOTA_CMD"), "dakota_runner.py", {"samples": 20, "seed": 1})
    assert run.output["moments"]["std_dev"] > 0
