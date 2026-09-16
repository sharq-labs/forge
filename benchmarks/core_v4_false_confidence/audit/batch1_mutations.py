"""Batch-1 guards, each disabled in place, its catching test run, the file restored and verified by digest.

Not in tests/mutation_guards.py: that file is certification-pinned, so new guards join it in the Core Freeze V4 round.
"""
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("D:/forge-audit")
sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

PY = sys.executable
SCRATCH = pathlib.Path(os.environ["SCRATCH"])
T = "tests/hybrid_uq/test_core_scientific_audit_batch1.py"

MUTATIONS = [
    ("B1a", "src/engcore/hybrid_uq/local_gaussian.py::_goodness_of_fit",
     "    if chi / dof > MISFIT_REFUSE_VARIANCE_RATIO:\n", "    if False:\n",
     T + "::test_core001_a_gross_misfit_is_refused_and_emits_no_covariance"),
    ("B1b", "src/engcore/hybrid_uq/local_gaussian.py::_goodness_of_fit",
     "    return set(), {RouteReason.RESIDUALS_EXCEED_DECLARED_NOISE}\n", "    return set(), set()\n",
     T + "::test_core001_a_moderate_misfit_is_downgraded_and_says_why"),
    ("B1c", "src/engcore/hybrid_uq/local_gaussian.py::local_gaussian_posterior",
     "    fit_refusals, fit_downgrades = _goodness_of_fit(chi_min, n, p)\n", "    fit_refusals, fit_downgrades = set(), set()\n",
     T + "::test_core001_a_gross_misfit_is_refused_and_emits_no_covariance"),
    ("B1d", "src/engcore/hybrid_uq/local_gaussian.py::_require_reasons_follow_measurements",
     "            found_refusals, found_downgrades = _goodness_of_fit(chi_minimum, n, p)\n",
     "            found_refusals, found_downgrades = set(d.refusals) & {RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE}, set(d.downgrades) & {RouteReason.RESIDUALS_EXCEED_DECLARED_NOISE}\n",
     T + "::test_a_record_that_hides_its_misfit_is_refused_on_read"),
    ("B1e", "src/engcore/hybrid_uq/local_gaussian.py::_tail_verdict",
     "    if ratio < TAIL_REFUSE_RATIO:\n", "    if False:\n",
     T + "::test_core003_a_tail_far_heavier_than_the_gaussian_is_refused"),
    ("B1f", "src/engcore/hybrid_uq/local_gaussian.py::local_gaussian_posterior",
     "                tail_ratio = min(tail_ratio, (value - chi_min) / radius ** 2)\n", "                pass\n",
     T + "::test_core003_a_tail_far_heavier_than_the_gaussian_is_refused"),
    ("B1g", "src/engcore/hybrid_uq/local_gaussian.py::_require_reasons_follow_measurements",
     "        found_refusals, found_downgrades = _tail_verdict(tail_ratio)\n",
     "        found_refusals, found_downgrades = set(d.refusals) & {RouteReason.TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN}, set()\n",
     T + "::test_a_record_that_hides_its_tail_is_refused_on_read"),
    ("B1h", "src/engcore/hybrid_uq/router.py::route_uncertainty",
     "        if misfit:\n", "        if False:\n",
     T + "::test_core001_a_misfit_is_not_rescued_by_rebuilding_a_grid"),
    ("B1i", "src/engcore/hybrid_uq/router.py::route_uncertainty",
     "            if not bound:\n", "            if False:\n",
     T + "::test_core002_a_grid_without_the_evidence_it_describes_is_not_certified"),
    ("B1j", "src/engcore/hybrid_uq/router.py::route_uncertainty",
     "                problem = grid_goodness_of_fit(grid, observations) or grid_containment(grid, calibration)\n",
     "                problem = grid_containment(grid, calibration)\n",
     T + "::test_core001_a_misfit_supplied_grid_is_passed_over"),
    ("B1k", "src/engcore/hybrid_uq/router.py::route_uncertainty",
     "                problem = grid_goodness_of_fit(grid, observations) or grid_containment(grid, calibration)\n",
     "                problem = grid_goodness_of_fit(grid, observations)\n",
     T + "::test_core002_a_supplied_grid_that_truncates_the_posterior_is_passed_over"),
    ("B1l", "src/engcore/hybrid_uq/router.py::route_uncertainty",
     "            require_grid_is_this_evidence(grid, calibration, observations, forward)\n", "            pass\n",
     T + "::test_core005_a_grid_computed_from_other_data_under_the_same_id_is_refused"),
    ("B1m", "src/engcore/hybrid_uq/_grid_evidence.py::require_grid_is_this_evidence",
     "        if not abs(chi_grid - chi_forward) <= tolerance:\n", "        if False:\n",
     T + "::test_core005_a_grid_computed_from_other_data_under_the_same_id_is_refused"),
    ("B1n", "src/engcore/hybrid_uq/_grid_evidence.py::require_grid_is_this_evidence",
     "            if usable[row]:\n", "            if False:\n",
     T + "::test_a_grid_whose_admission_disagrees_with_the_forward_model_is_refused"),
    ("B1o", "src/engcore/hybrid_uq/_grid_evidence.py::grid_containment",
     "            if peak - face_peak >= EDGE_LOG_LIKELIHOOD_DROP:\n", "            if True:\n",
     T + "::test_core002_a_parameter_the_data_never_touch_is_not_certified_on_a_supplied_grid"),
    ("B1p", "src/engcore/hybrid_uq/router.py::_rebuild_grid",
     "    if dominated:\n", "    if False:\n",
     "tests/hybrid_uq/test_hybrid_uq_router.py::test_a_rebuilt_grid_whose_posterior_spans_both_declared_bounds_is_not_used"),
    ("B1q", "src/engcore/hybrid_uq/predictive.py::_grid_evidence_judgement",
     "    if observations is None:\n        return RouteClaim.DOWNGRADED, (RouteReason.GRID_NOT_BOUND_TO_EVIDENCE,)\n",
     "    if observations is None:\n        return claim, ()\n",
     "tests/hybrid_uq/test_audit_hybrid_grid_route.py::test_huq02_a_resolved_grid_is_still_supported_through_the_same_judgement"),
]

for mid, spec, old, new, test in MUTATIONS:
    path = ROOT / spec.partition("::")[0]
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    try:
        applied = M._apply(ROOT, spec, old, new)
        if isinstance(applied, str):
            print(mid, "->", applied)
            continue
        done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'pt' / ('b1_' + mid)}", test],
                              cwd=ROOT, capture_output=True, text=True)
        last = [l for l in done.stdout.splitlines() if l.strip()][-1]
        print(mid, test.split("::")[-1], "->", "KILLED" if done.returncode != 0 else "SURVIVED", "|", last, flush=True)
    finally:
        path.write_bytes(original)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
# control
done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'pt' / 'b1_control'}",
                       *sorted({m[4] for m in MUTATIONS})], cwd=ROOT, capture_output=True, text=True)
print("CONTROL (unmutated)", "GREEN" if done.returncode == 0 else "RED", "|", [l for l in done.stdout.splitlines() if l.strip()][-1])
