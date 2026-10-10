"""Roadmap V2 R8: discovery providers own algorithms, FORGE owns authority (PySINDy, BoTorch, Dakota adapters).

These tests use canned provider payloads and never skip.  Live provider runs are an explicit, opt-in smoke tool outside
the test tiers: ``python -m tools.discovery_provider_smoke --discovery-cmd '[...]' --dakota-cmd '[...]'``."""

from __future__ import annotations

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
