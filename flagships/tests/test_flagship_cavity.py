"""FLAGSHIP C gates: real OpenFOAM + SU2 (+ CoolProp) through the BIG 12 runtime (WSL `sci` env), with the preserved OpenFOAM/SU2 disagreement."""

from __future__ import annotations

import pytest

from engcore.engineering import LevelStatus, committed_artifacts, verify_bundle, write_bundle
from engcore.system_runtime import Availability, RunStatus, compare_runs, trace_result

try:
    from engcore.providers import default_registry
    REG = default_registry()
    OK = all(REG.status(p).available for p in ("openfoam", "su2", "coolprop"))
except Exception:  # pragma: no cover
    OK = False
pytestmark = pytest.mark.skipif(not OK, reason="OpenFOAM, SU2 and CoolProp are all required")

if OK:
    from forge_flagships import cavity_cfd as cf


@pytest.fixture(scope="module")
def run():
    return cf.run_cavity(registry=REG)


def o(run, oid):
    ob = run.result.observable(oid)
    assert ob.availability is Availability.AVAILABLE, (oid, ob.reason)
    return ob.value.value.magnitude


def test_gate_c_real_openfoam_and_su2_run_on_identical_declared_inputs_at_three_meshes(run):
    assert run.result.status is RunStatus.SUCCEEDED
    assert {p.provider_id for p in run.result.provider_records} == {"coolprop", "openfoam", "su2"}
    assert o(run, "lid_velocity") * cf.SIDE / o(run, "kinematic_viscosity") == pytest.approx(100.0, rel=1e-9)     # Re is exactly the declared value
    # both codes receive the same lid speed and fluid records (same producer identity for the shared inputs)
    for n in cf.LEVELS:
        a, b = run.result.receipt(f"openfoam_{n}"), run.result.receipt(f"su2_{n}")
        assert set(a.input_digests) == set(b.input_digests) and len(a.input_digests) == 3


def test_the_predeclared_whole_field_disagreement_is_preserved_at_every_mesh_and_is_lid_adjacent(run):
    """The BIG 11 negative result, not hidden and not loosened: 3 % of lid speed, whole field."""
    for n in cf.LEVELS:
        assert o(run, f"whole_field_within_tolerance_{n}") == 0.0
        assert o(run, f"whole_field_max_difference_{n}") > 0.2                            # > 20 % of lid speed
        assert o(run, f"max_difference_cell_y_{n}") > 0.95                                # in the cell layer next to the moving lid
    l5 = run.ladder.entry(5)
    assert l5.status is LevelStatus.ATTEMPTED_NOT_REACHED and "the disagreement is the result" in l5.note
    assert run.ladder.entry(2).status is LevelStatus.ATTEMPTED_NOT_REACHED and "su2" in run.ladder.entry(2).note
    post = [e for e in l5.evidence if e.classification.startswith("post_hoc_")]
    assert len(post) == len(cf.LEVELS)                                                 # the lower-half comparisons exist but are labelled post hoc
    assert run.ladder.corroboration_reached is False


def test_both_codes_are_compared_with_the_published_numerical_benchmark_at_the_finest_mesh(run):
    assert len(run.comparisons) == 2
    for c in run.comparisons:
        assert c.reference_kind.value == "benchmark_dataset" and c.classification == "numerical_benchmark_comparison_not_validation_grant"
        assert c.applicability.status == "within"
    assert run.ladder.entry(6).status is LevelStatus.REACHED                           # recorded outcome of the predeclared 2 % criterion at 80x80
    assert run.ladder.reference_level_reached == "published_numerical_benchmark"
    assert run.ladder.entry(7).status is LevelStatus.NOT_AVAILABLE                     # never experimental


def test_the_predeclared_monotone_convergence_criterion_is_not_met_for_openfoam_and_that_is_visible(run):
    assert o(run, "ghia_u_max_error_of_decreasing") == 0.0                             # OpenFOAM error: 0.0127, 0.0027, 0.0044 - not monotone
    assert o(run, "ghia_u_max_error_su2_decreasing") == 1.0
    l4 = run.ladder.entry(4)
    assert l4.status is LevelStatus.ATTEMPTED_NOT_REACHED and "benchmark-relative" in l4.note
    assert {e.classification for e in l4.evidence} == {"discretisation_convergence", "post_hoc_discretisation_convergence"}


def test_flow_diagnostics_are_reported_and_the_codes_agree_on_the_vortex_position_to_a_cell(run):
    n = cf.LEVELS[-1]
    dx = 1.0 / n
    assert abs(o(run, f"vortex_x_openfoam_{n}") - o(run, f"vortex_x_su2_{n}")) <= dx + 1e-9
    assert abs(o(run, f"vortex_y_openfoam_{n}") - o(run, f"vortex_y_su2_{n}")) <= 2 * dx + 1e-9
    assert o(run, f"u_flux_residual_openfoam_{n}") < cf.FLUX_TOL
    assert run.summary.scientific_status == "insufficient_evidence"


def test_negative_controls_an_unsupported_regime_and_an_inapplicable_benchmark():
    out = cf.negative_controls(REG)
    assert out["unsupported_regime"]["openfoam"] == "failed" and "laminar" in out["unsupported_regime"]["reason"] and out["unsupported_regime"]["outputs_available"] == []
    assert out["benchmark_not_applicable"]["outcome"] == "not_applicable"              # a perfect number does not rescue a benchmark that does not apply


def test_result_trace_and_reproducibility(run, tmp_path):
    trace = trace_result(run.result, "ghia_u_max_error_openfoam_80")
    assert trace.complete, trace.gaps
    assert {"provider", "provider_execution", "node", "system", "scenario"} <= set(trace.levels())
    d = str(tmp_path / "b")
    manifest = write_bundle(d, name="c", request=run.cavity.request, result=run.result, summary=run.summary, references=list(run.references), artifacts=committed_artifacts(run.result, run.cavity.exchange.files))
    assert verify_bundle(d).digest == manifest.digest
    again = cf.run_cavity(registry=REG)
    cmp_ = compare_runs(run.result, again.result, rel_tol=1e-6, non_deterministic_nodes=tuple(f"{p}_{n}" for p in ("openfoam", "su2") for n in cf.LEVELS))
    assert cmp_.identity_replay                                                       # the same computation was set up again
    assert again.result.request_digest == run.result.request_digest
