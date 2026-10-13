"""Rebuild into private output trees; readers must inspect those bytes, never stale reports."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.mark.expensive
@pytest.mark.parametrize("round_name", ["empirical_validation", "model_measurement_validation"])
def test_rebuild_preserves_published_bytes_and_checks_only_its_own_output(round_name, tmp_path):
    # Each round declares its reference import root in its existing test module.
    importlib.import_module(f"benchmarks.{round_name}.tests.test_{round_name}")
    builder = importlib.import_module(f"benchmarks.{round_name}.audit.build_gates")
    checker = importlib.import_module(f"benchmarks.{round_name}.audit.check_consistency")
    source = Path(builder.ROOT)
    before = {p.name: p.read_bytes() for p in source.iterdir() if p.suffix in (".json", ".md")}
    output = tmp_path / "private" / round_name
    try:
        payload = builder.build(output_dir=output)
        assert (output / "SAFETY_GATES.json").is_file()
        assert (output / "CONSISTENCY_AUDIT.json").is_file()
        assert checker.run(artifact_dir=output) == payload["consistency"]
        # Corrupt only this run's result. The checker must read the changed run,
        # even though valid published data still exist in the source directory.
        results_path = output / "VALIDATION_RESULTS.json"
        results = json.loads(results_path.read_text())
        if round_name == "empirical_validation":
            results["primary"]["rows"] += 10000
        else:
            results["row_counts"]["VALIDATION"] += 10000
        results_path.write_text(json.dumps(results), encoding="utf-8")
        assert checker.run(artifact_dir=output)["inconsistencies"] > payload["consistency"]["inconsistencies"]
        results_path.unlink()
        with pytest.raises(FileNotFoundError):
            checker.run(artifact_dir=output)
    finally:
        assert {p.name: p.read_bytes() for p in source.iterdir() if p.suffix in (".json", ".md")} == before
