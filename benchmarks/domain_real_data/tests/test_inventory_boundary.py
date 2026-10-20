"""New paths must not inherit scientific provenance from a directory."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


def scanner():
    path = Path(__file__).resolve().parents[1] / "audit" / "inventory_scan.py"
    spec = importlib.util.spec_from_file_location("_inventory_boundary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", [
    "docs/new_measurements.csv",
    "benchmarks/new_measurements.csv",
    "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv",
])
def test_new_file_has_unknown_provenance_even_under_known_prefix(path):
    assert scanner().classify(path)[1] == "UNKNOWN_PROVENANCE"


def test_historical_scan_replays_exact_original_bytes():
    scan = scanner()
    assert scan.render(scan.historical_scan()) == scan.OUT.read_bytes()


def test_missing_historical_object_fails_closed(monkeypatch):
    scan = scanner()
    monkeypatch.setattr(scan, "HISTORICAL_COMMIT", "0" * 40)
    with pytest.raises(RuntimeError, match="historical"):
        scan.historical_scan()


@pytest.fixture
def git_inventory(tmp_path, monkeypatch):
    scan = scanner()
    # Load the immutable original program before selecting a synthetic Git checkout.
    original_program = getattr(scan, "_historical_program", lambda: None)()
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    git("init", "-q")
    path = "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/sample.csv"
    file = root / path
    file.parent.mkdir(parents=True)
    file.write_bytes(b"measurement\n1\n")
    git("add", ".")
    blob = git("hash-object", "--no-filters", path)
    monkeypatch.setattr(scan, "ROOT", root)
    monkeypatch.setattr(scan, "_historical_entries", lambda: {path: blob})
    if original_program is not None:
        monkeypatch.setattr(scan, "_historical_program", lambda: original_program)
    return scan, root, path, git


def test_unicode_staged_addition_is_enumerated_as_unknown(git_inventory):
    scan, root, _, git = git_inventory
    path = "docs/قياس.csv"
    (root / "docs").mkdir()
    (root / path).write_bytes(b"not reviewed\n")
    git("add", ".")
    report = scan.scan()
    assert any(path in g.get("files", []) and g["class"] == "UNKNOWN_PROVENANCE"
               for g in report["groups"])


def test_unchanged_historical_measurement_retains_class(git_inventory):
    scan, _, path, _ = git_inventory
    assert scan.classify(path)[1] == "REAL_MEASURED"


@pytest.mark.parametrize("stage", [False, True])
def test_actual_modified_measurement_is_unknown(git_inventory, stage):
    scan, root, path, git = git_inventory
    (root / path).write_bytes(b"changed\n")
    if stage:
        git("add", path)
    assert scan.classify(path)[1] == "UNKNOWN_PROVENANCE"


def test_assume_unchanged_does_not_hide_modified_measurement(git_inventory):
    scan, root, path, git = git_inventory
    git("update-index", "--assume-unchanged", path)
    (root / path).write_bytes(b"changed behind index flag\n")
    assert scan.classify(path)[1] == "UNKNOWN_PROVENANCE"
