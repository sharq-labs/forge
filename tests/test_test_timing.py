"""tools/test_timing.py -- developer timing telemetry and the large-slowdown guard.

Telemetry, never evidence: nothing here can change a test outcome. The guard flags
only changes that clear both an absolute and a relative bar set above measured noise.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools import test_timing


def _report(**changes):
    base = {"schema": test_timing.SCHEMA, "workers": 4, "tests_reported": 100, "wall_seconds": 100.0,
            "modules": {"tests/a.py": 10.0, "tests/b.py": 1.0}, "tests": {"tests/a.py::t": 4.0}}
    base.update(changes)
    return base


def test_noise_sized_changes_are_not_flagged() -> None:
    noisy = _report(wall_seconds=125.0, modules={"tests/a.py": 12.5, "tests/b.py": 1.9}, tests={"tests/a.py::t": 5.8})
    assert test_timing.compare(_report(), noisy) == []


@pytest.mark.parametrize("change, expected", [
    ({"modules": {"tests/a.py": 21.0, "tests/b.py": 1.0}}, "module tests/a.py"),
    ({"tests": {"tests/a.py::t": 8.5}}, "test tests/a.py::t"),
    ({"wall_seconds": 150.0}, "wall"),
])
def test_a_large_slowdown_is_flagged(change, expected) -> None:
    found = test_timing.compare(_report(), _report(**change))
    assert len(found) == 1 and found[0].startswith(expected)


def test_a_big_ratio_on_a_tiny_module_or_a_big_delta_at_low_ratio_is_not_flagged() -> None:
    assert test_timing.compare(_report(), _report(modules={"tests/a.py": 10.0, "tests/b.py": 4.0})) == []  # x4 but +3 s
    assert test_timing.compare(_report(), _report(modules={"tests/a.py": 18.0, "tests/b.py": 1.0})) == []  # +8 s but x1.8


def test_whole_run_wall_is_compared_only_between_runs_of_the_same_shape() -> None:
    assert test_timing.compare(_report(), _report(wall_seconds=300.0, workers=1)) == []
    assert test_timing.compare(_report(), _report(wall_seconds=300.0, tests_reported=5000)) == []


def test_the_plugin_records_telemetry_and_never_changes_an_outcome(tmp_path) -> None:
    (tmp_path / "test_sample.py").write_text(
        "import time\n\ndef test_ok():\n    time.sleep(0.3)\n\ndef test_bad():\n    assert False\n", encoding="utf-8")
    report = tmp_path / "out" / "timing.json"
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tools.test_timing",
                          f"--timing-report={report}", str(tmp_path / "test_sample.py")],
                         capture_output=True, text=True, cwd=str(test_timing.pathlib.Path(__file__).resolve().parents[1]))
    assert run.returncode == 1 and "1 failed, 1 passed" in run.stdout  # the failure stays a failure
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["schema"] == test_timing.SCHEMA and "not scientific evidence" in data["classification"]
    assert data["outcomes"] == {"failed": 1, "passed": 1} and len(data["failed"]) == 1
    assert data["tests_reported"] == 2 and data["python"] and data["machine"]["logical_cpus"]
    (module,) = data["modules"]
    assert module.endswith("test_sample.py") and data["modules"][module] >= 0.3
    assert any(name.endswith("test_ok") for name in data["tests"])


def test_compare_and_history_commands(tmp_path, capsys) -> None:
    old, new = tmp_path / "a.json", tmp_path / "b.json"
    old.write_text(json.dumps(_report()), encoding="utf-8")
    new.write_text(json.dumps(_report(modules={"tests/a.py": 30.0, "tests/b.py": 1.0}, failed=[], python="3.x")), encoding="utf-8")
    assert test_timing.main(["compare", str(old), str(old)]) == 0
    assert test_timing.main(["compare", str(old), str(new)]) == 1
    assert "SLOWER: module tests/a.py" in capsys.readouterr().out
    old.write_text(json.dumps(_report(failed=[], python="3.x")), encoding="utf-8")
    assert test_timing.main(["history", str(tmp_path)]) == 0
    assert "wall" in capsys.readouterr().out


def test_the_default_history_lives_outside_the_repository(monkeypatch) -> None:
    root = test_timing.pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.delenv("FORGE_TIMING_DIR", raising=False)
    assert root not in test_timing.default_history_dir().parents
