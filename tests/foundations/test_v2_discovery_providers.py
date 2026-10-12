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



# ---- run_provider: the process boundary is bounded and every failure is a typed refusal ------------


@pytest.fixture
def runners(tmp_path, monkeypatch):
    import engcore.claims.discovery_providers as dp

    monkeypatch.setattr(dp, "RUNNERS", tmp_path.resolve())

    def write(name, source):
        (tmp_path / name).write_text(source, encoding="utf-8")
        return name
    return write


def test_a_runner_returns_a_digest_bound_provider_run(runners):
    import sys

    name = runners("echo_runner.py", "import json, sys\nreq = json.load(sys.stdin)\n"
                                     "print(json.dumps({'provider': 'echo', 'provider_version': '1', 'echo': req}))\n")
    run = run_provider([sys.executable, "-I"], name, {"x": [1, 2]})
    assert run.provider == "echo" and run.output["echo"] == {"x": [1, 2]} and len(run.runner_digest) == 64


def test_a_runner_that_outlives_its_timeout_is_refused_not_raised_raw(runners):
    import sys
    import time

    name = runners("slow_runner.py", "import time\ntime.sleep(60)\n")
    start = time.perf_counter()
    with pytest.raises(ProviderRefused, match="did not finish within"):
        run_provider([sys.executable, "-I"], name, {}, timeout=1.0)
    assert time.perf_counter() - start < 30.0


@pytest.mark.parametrize("source", ["print('not json')\n", "print('[1, 2]')\n", ""])
def test_a_runner_that_writes_no_json_object_is_refused(runners, source):
    import sys

    name = runners("bad_runner.py", source)
    with pytest.raises(ProviderRefused, match="no JSON result|not a JSON object"):
        run_provider([sys.executable, "-I"], name, {})


def test_an_interpreter_that_cannot_be_launched_is_refused(runners, tmp_path):
    name = runners("any_runner.py", "print('{}')\n")
    with pytest.raises(ProviderRefused, match="could not run"):
        run_provider([str(tmp_path / "no-such-interpreter.exe")], name, {})



# ---- the Dakota runner: a missing, hung or silent dakota is a typed refusal with its reason ----------


def _fake_dakota(directory, version_body: str) -> None:
    script = directory / "dakota"
    script.write_text("#!/bin/sh\n"
                      'if [ "$1" = "-version" ]; then\n' + version_body + "\n  exit 0\nfi\n"
                      "echo 'response_fn_1  1.0e+00  1.0e-01  0.0e+00  3.0e+00'\n", encoding="utf-8")
    script.chmod(0o755)


def test_a_missing_dakota_is_refused_with_its_reason():
    import shutil
    import sys

    if shutil.which("dakota"):
        pytest.skip("a real dakota is on PATH here")
    with pytest.raises(ProviderRefused, match="dakota executable not found on PATH"):
        run_provider([sys.executable, "-I"], "dakota_runner.py", {"samples": 2, "seed": 1}, timeout=120)


@pytest.mark.skipif(__import__("os").name != "posix", reason="a fake dakota needs a POSIX shell script on PATH")
@pytest.mark.parametrize("body, reason", [("  sleep 60", r"dakota -version did not finish within 1s"),
                                          ("  :", r"dakota -version printed nothing")])
def test_a_hung_or_silent_dakota_version_probe_is_a_bounded_refusal(tmp_path, monkeypatch, body, reason):
    import os
    import sys
    import time

    _fake_dakota(tmp_path, body)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    start = time.perf_counter()
    with pytest.raises(ProviderRefused, match=reason):
        run_provider([sys.executable, "-I"], "dakota_runner.py", {"samples": 2, "seed": 1, "version_timeout_s": 1}, timeout=120)
    assert time.perf_counter() - start < 30.0
