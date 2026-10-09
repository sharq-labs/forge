"""Big Rock O: the general geometry vertical slice, end to end (architecture proof, never validation)."""

from __future__ import annotations

import pytest

from engcore.scientific.units.quantity import Quantity
from engcore.spatial.providers import gmsh_available

GMSH_OK, GMSH_DETAIL = gmsh_available()
needs_gmsh = pytest.mark.skipif(not GMSH_OK, reason=f"Gmsh unavailable: {GMSH_DETAIL}")


def mm(v):
    return Quantity(v, "mm")


VALUES = {"t_structural": mm(100), "t_insulation": mm(80), "height": Quantity(0.2, "m")}


def test_material_path_is_sourced_and_labelled_illustrative():
    from forge_flagships.geometry_slice import PROPERTY_SETS, SliceConditions, resolved_conductivities, series_solution

    k = resolved_conductivities(SliceConditions())
    assert k["structural"].status == "known" and k["structural"].value.value.magnitude == 1.0
    for props in PROPERTY_SETS.values():
        assert "NOT reference data" in props.snapshot.sources[0].issuer
    q, t_int = series_solution(0.1, 0.08, 1.0, 0.04, 400.0, 300.0)
    assert q == pytest.approx(100 / 2.1) and t_int == pytest.approx(400 - q * 0.1)


@needs_gmsh
def test_slice_runs_end_to_end_and_ends_at_insufficient_evidence():
    from forge_flagships.geometry_slice import run_slice

    r = run_slice(VALUES)
    d = r.to_dict()
    assert d["classification"] == "architecture_proof_not_validation" and d["verdict"] == "insufficient_evidence"
    assert all(v < 1e-12 for v in r.geometric_checks.values())
    assert r.analytic["heat_flux"] == pytest.approx(100 / 2.1)
    assert r.criteria_met is False and "max-heat-flux" in r.criteria_reason
    roles = {e.role.value for e in r.revision.evidence}
    assert "validation" not in roles and "measurement" not in roles and r.revision.is_candidate
    assert r.revision.uncertainty_of("heat_flux").status.value == "unknown"
    assert r.revision.geometry_variant_ids == (r.variant_id,) and r.geometry_digest in r.revision.geometry_digests
    if r.numerical["status"] == "ran":  # FEniCSx present: P1 on a conforming mesh reproduces the piecewise-linear solution
        assert r.numerical["abs_difference_from_closed_form_K"] < 1e-6 and "verification" in roles
    else:
        assert r.numerical["status"] == "provider_unavailable" and "verification" not in roles
        assert "not attempted" in d["evidence_stop"]["analytic_limit"]


@needs_gmsh
def test_changing_a_dimension_changes_every_bound_identity():
    from forge_flagships.geometry_slice import run_slice

    a = run_slice(VALUES)
    b = run_slice(dict(VALUES, t_insulation=mm(81)))
    for attr in ("geometry_digest", "variant_id", "mesh_digest", "pde_problem_digest"):
        assert getattr(a, attr) != getattr(b, attr)
    assert a.revision.context_digest != b.revision.context_digest
    assert a.to_dict() == run_slice(VALUES).to_dict()  # deterministic


def test_campaign_is_deterministic_and_never_supports_above_the_rung_that_ran():
    from forge_flagships.geometry_slice import run_slice_campaign

    run = run_slice_campaign(12)
    assert run.digest == run_slice_campaign(12).digest
    assert run.to_dict()["classification"] == "search_record_not_validation"
    for key, (standing, rank, why) in run.standings().items():
        if standing == "supported":
            assert rank is not None and (rank < 2 or why)  # rung 2 decides only if a real provider ran
            assert "supported is not validated" in why
    promoted = [p for p in run.promotions if p.promoted]
    assert promoted and all("not a verdict" in p.reason for p in promoted)
