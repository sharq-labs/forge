"""Fresh-process imports stay light; actual selection retains its ledger boundary."""
import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest


def test_units_arm_import_does_not_initialize_claim_assessment():
    root = pathlib.Path(__file__).resolve().parents[2]
    code = f"""
import sys
sys.path[:0] = [{str(root)!r}, {str(root / 'src')!r}]
import benchmarks.genesis_lite.arms_v4
assert 'engcore.claims' not in sys.modules
assert 'engcore.claims.assessment' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                            env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}, timeout=30)
    assert result.returncode == 0, result.stderr


def test_selection_ledger_failure_still_propagates(monkeypatch):
    from engcore.claims import multiplicity
    from engcore.mind.grammar import select

    def unavailable(*args, **kwargs):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(multiplicity.MultiplicityLedger, "__init__", unavailable)
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        select([], np.zeros((4, 1)), np.zeros(4), sigma=0.1, ledger_id="import-boundary")
