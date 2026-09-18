"""Batch-2 guards, each disabled in place, its catching test run, the file restored and verified by digest.

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
T = "tests/hybrid_uq/test_core_scientific_audit_batch2.py"

MUTATIONS = [
    ("B2a", "src/engcore/inference/calibration.py::assess_identifiability",
     "    eigenvalues = np.linalg.eigvalsh(correlation)\n", "    eigenvalues = np.linalg.eigvalsh(covariance)\n",
     T + "::test_core004_the_grid_verdict_does_not_depend_on_the_unit_of_a_parameter"),
    ("B2b", "src/engcore/hybrid_uq/identifiability.py::classify",
     "    eigenvalues = np.linalg.eigvalsh(correlation)\n", "    eigenvalues = np.linalg.eigvalsh(cov)\n",
     T + "::test_core004_the_local_verdict_does_not_depend_on_the_unit_of_a_parameter"),
    ("B2c", "src/engcore/hybrid_uq/identifiability.py::_rule",
     "    return status, why + WIDTH_REFERENCE_NOTE\n", "    return status, why\n",
     T + "::test_core004_the_verdict_says_its_widths_are_relative_to_each_parameters_declared_zero"),
    ("B2d", "src/engcore/hybrid_uq/_grid_evidence.py::grid_prior_uniformity",
     "        if not worst <= UNIFORM_STEP_RELATIVE_TOLERANCE * mean:\n", "        if False:\n",
     T + "::test_core010_a_grid_not_uniform_in_the_inference_coordinate_is_passed_over"),
    ("B2e", "src/engcore/hybrid_uq/_grid_evidence.py::grid_prior_uniformity",
     "            axis = np.log(axis)\n", "            pass\n",
     T + "::test_core010_a_log_spaced_grid_is_the_declared_prior_of_a_log_parameter"),
    ("B2f", "src/engcore/hybrid_uq/router.py::route_uncertainty",
     "                problem = (grid_prior_uniformity(grid, calibration) or grid_goodness_of_fit(grid, observations)\n",
     "                problem = (None or grid_goodness_of_fit(grid, observations)\n",
     T + "::test_core010_a_grid_not_uniform_in_the_inference_coordinate_is_passed_over"),
    ("B2g", "src/engcore/hybrid_uq/predictive.py::_grid_evidence_judgement",
     "    problem = (grid_prior_uniformity(posterior, calibration) or grid_goodness_of_fit(posterior, observations)\n",
     "    problem = (None or grid_goodness_of_fit(posterior, observations)\n",
     T + "::test_core010_the_standalone_grid_predictive_refuses_an_undeclared_prior_given_the_evidence"),
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
        done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / ('b2_' + mid)}", test],
                              cwd=ROOT, capture_output=True, text=True)
        last = [l for l in done.stdout.splitlines() if l.strip()][-1]
        print(mid, test.split("::")[-1], "->", "KILLED" if done.returncode != 0 else "SURVIVED", "|", last, flush=True)
    finally:
        path.write_bytes(original)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'b2_control'}",
                       *sorted({m[4] for m in MUTATIONS})], cwd=ROOT, capture_output=True, text=True)
print("CONTROL (unmutated)", "GREEN" if done.returncode == 0 else "RED", "|", [l for l in done.stdout.splitlines() if l.strip()][-1])
