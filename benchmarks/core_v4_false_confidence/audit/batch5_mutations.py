"""Batch-5 guards, each disabled in place, its catching test run, the file restored and verified by digest.

Not in tests/mutation_guards.py: that file is certification-pinned, so new guards join it in the Core Freeze V4 round.
Run from the repository root with SCRATCH set to a scratch directory.
"""
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

PY = sys.executable
SCRATCH = pathlib.Path(os.environ["SCRATCH"])
T = "tests/test_core_scientific_audit_batch5.py"

MUTATIONS = [
    ("B5a", "src/engcore/inference/split.py::ObservationSplit.__post_init__",
     "            if near:\n", "            if False:\n",
     T + "::test_core017_a_copied_reading_nudged_below_measurement_resolution_is_leakage"),
    ("B5b", "src/engcore/scientific/models/definition.py::CrossLimitCondition.__post_init__",
     "            if self.maximum.magnitude_in(self.minimum.units) < self.minimum.magnitude:\n",
     "            if self.maximum.magnitude < self.minimum.magnitude:\n",
     T + "::test_core018_cross_limit_bounds_are_ordered_in_one_unit"),
    ("B5c", "src/engcore/scientific/consensus.py::CrossSolverConsensus.from_results",
     "                str(name): float(quantity.magnitude_in(common_unit.get(str(name), quantity.units)))\n",
     "                str(name): float(quantity.magnitude_in(quantity.units))\n",
     "tests/test_audit_consensus_execution_binding.py::test_core018_the_same_length_in_metres_and_millimetres_agrees"),
]

for mid, spec, old, new, test in MUTATIONS:
    path = ROOT / spec.partition("::")[0]
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    try:
        applied = M._apply(ROOT, spec, old, new)
        if isinstance(applied, str):
            print(mid, "->", applied, flush=True)
            continue
        done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / ('b5_' + mid)}", test],
                              cwd=ROOT, capture_output=True, text=True)
        last = [l for l in done.stdout.splitlines() if l.strip()][-1]
        print(mid, test.split("::")[-1], "->", "KILLED" if done.returncode != 0 else "SURVIVED", "|", last, flush=True)
    finally:
        path.write_bytes(original)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'b5_control'}",
                       *sorted({m[4] for m in MUTATIONS})], cwd=ROOT, capture_output=True, text=True)
print("CONTROL (unmutated)", "GREEN" if done.returncode == 0 else "RED", "|", [l for l in done.stdout.splitlines() if l.strip()][-1])
