"""Production discovery modules must not cause pytest to duplicate engcore."""
import pathlib
import subprocess
import sys


def test_collecting_discovery_directory_preserves_canonical_package():
    root = pathlib.Path(__file__).resolve().parents[2]
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "src/engcore/scientific/discovery",
                          "tests/test_trust_boundary_package_identity.py::test_the_frozen_spelling_is_the_canonical_package_not_a_copy"],
                         cwd=root, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "1 passed" in run.stdout
