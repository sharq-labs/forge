"""Batch-3b guards, each disabled in place, its catching test run, the file restored and verified by digest.

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
T = "tests/test_core_scientific_audit_batch3b.py"

MUTATIONS = [
    ("B3f", "src/engcore/scientific/oracles.py::OracleEvidenceSet.compare",
     "        if elsewhere:\n", "        if False:\n",
     T + "::test_core009_a_comparison_at_other_conditions_is_not_made"),
    ("B3g", "src/engcore/scientific/oracles.py::_same_operating_point",
     "    return a == b or abs(a - b) <= _OPERATING_POINT_RTOL * max(abs(a), abs(b))\n", "    return True\n",
     T + "::test_core009_a_comparison_at_other_conditions_is_not_made"),
    ("B3h", "src/engcore/scientific/results/result.py::ScientificResult._checked_validity",
     "                if name in inputs and not _same_operating_point(value, inputs[name]):\n", "                if False:\n",
     T + "::test_core014_an_assessment_read_at_another_operating_point_is_refused"),
    ("B3i", "src/engcore/scientific/models/definition.py::ValidityDomain.assess",
     "            evaluated = {key: value for key, value in merged.items() if key in read and isinstance(value, Quantity)}\n",
     "            evaluated = {}\n",
     T + "::test_core014_an_assessment_read_at_another_operating_point_is_refused"),
    ("B3j", "src/engcore/scientific/results/uncertainty.py::Uncertainty.from_dict",
     '            source_kind=UncertaintySource(payload.get("source_kind", UncertaintySource.UNSPECIFIED.value)),\n', "",
     T + "::test_core016_an_uncertainty_says_what_kind_of_uncertainty_it_is"),
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
        done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / ('b3b_' + mid)}", test],
                              cwd=ROOT, capture_output=True, text=True)
        last = [l for l in done.stdout.splitlines() if l.strip()][-1]
        print(mid, test.split("::")[-1], "->", "KILLED" if done.returncode != 0 else "SURVIVED", "|", last, flush=True)
    finally:
        path.write_bytes(original)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'b3b_control'}",
                       *sorted({m[4] for m in MUTATIONS})], cwd=ROOT, capture_output=True, text=True)
print("CONTROL (unmutated)", "GREEN" if done.returncode == 0 else "RED", "|", [l for l in done.stdout.splitlines() if l.strip()][-1])
