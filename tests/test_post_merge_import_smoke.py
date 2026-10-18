"""Fresh processes expose import cycles hidden by a collected module cache."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("entry", ["engcore.data", "engcore.scientific", "engcore.numerical"])
def test_scientific_entry_points_import_in_a_fresh_process(entry):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(root / "src"), env.get("PYTHONPATH", "")) if p
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", f"import {entry}"],
        cwd=root, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
