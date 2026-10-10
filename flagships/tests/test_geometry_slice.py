"""Big Rock O: the general geometry vertical slice, end to end (architecture proof, never validation)."""

from __future__ import annotations

import pytest

from engcore.scientific.units.quantity import Quantity
from engcore.spatial.providers import gmsh_available

GMSH_OK, GMSH_DETAIL = gmsh_available()
needs_gmsh = pytest.mark.skipif(not GMSH_OK, reason=f"Gmsh unavailable: {GMSH_DETAIL}")


def mm(v):
    return Quantity(v, "mm")


def K(v):
    return Quantity(v, "K")


VALUES = {"t_structural": mm(100), "t_insulation": mm(80), "height": Quantity(0.2, "m")}


def conditions(hot=400, cold=300):
    from forge_flagships.geometry_slice import SliceConditions

    return SliceConditions(K(hot), K(cold), Quantity(25, "W/m^2"), K(395))


MESH = mm(10)


def test_material_path_is_sourced_and_labelled_illustrative():
    from forge_flagships.geometry_slice import PROPERTY_SETS, resolved_conductivities, series_solution

    k = resolved_conductivities(conditions())
    assert k["structural"].status == "known" and k["structural"].value.value.magnitude == 1.0
    for props in PROPERTY_SETS.values():
        assert "NOT reference data" in props.snapshot.sources[0].issuer
    q, t_int = series_solution(0.1, 0.08, 1.0, 0.04, 400.0, 300.0)
    assert q == pytest.approx(100 / 2.1) and t_int == pytest.approx(400 - q * 0.1)


@needs_gmsh
def test_slice_runs_end_to_end_and_ends_at_insufficient_evidence():
    from forge_flagships.geometry_slice import run_slice

    r = run_slice(VALUES, conditions=conditions(), mesh_size=MESH)
    d = r.to_dict()
    assert d["classification"] == "architecture_proof_not_validation" and d["verdict"] == "insufficient_evidence"
    assert d["conditions"] and d["mesh_size_m"] == pytest.approx(0.01)
    assert all(v < 1e-12 for v in r.geometric_checks.values())
    assert r.analytic["heat_flux"] == pytest.approx(100 / 2.1)
    assert r.criteria_met is False and "max-heat-flux" in r.criteria_reason
    assert r.evaluation.eligibility.value == "ranked_without_assessment"  # illustrative data is never selection-eligible
    assert r.evaluation.result.provenance.metadata["material_data_classification"] == "illustrative_not_reference_data"
    roles = {e.role.value for e in r.revision.evidence}
    assert "validation" not in roles and "measurement" not in roles and r.revision.is_candidate
    assert r.revision.uncertainty_of("heat_flux").status.value == "unknown"
    assert r.revision.geometry_variant_ids == (r.variant_id,) and r.geometry_digest in r.revision.geometry_digests
    if r.numerical["status"] == "ran":  # FEniCSx present: verification only within the declared tolerance
        assert ("verification" in roles) == (r.numerical["verification"] == "met")
    else:
        assert r.numerical["status"] == "provider_unavailable" and "verification" not in roles
        assert "not attempted" in d["evidence_stop"]["analytic_limit"]


@needs_gmsh
def test_every_result_changing_input_moves_the_bound_identities():
    from forge_flagships.geometry_slice import run_slice

    a = run_slice(VALUES, conditions=conditions(), mesh_size=MESH)
    b = run_slice(dict(VALUES, t_insulation=mm(81)), conditions=conditions(), mesh_size=MESH)
    for attr in ("geometry_digest", "variant_id", "mesh_digest", "pde_problem_digest"):
        assert getattr(a, attr) != getattr(b, attr)
    c = run_slice(VALUES, conditions=conditions(hot=410), mesh_size=MESH)
    assert c.evaluation.evaluation_id != a.evaluation.evaluation_id and c.revision.context_digest != a.revision.context_digest
    assert c.pde_problem_digest != a.pde_problem_digest
    m = run_slice(VALUES, conditions=conditions(), mesh_size=mm(20))
    assert m.mesh_digest != a.mesh_digest and m.pde_problem_digest != a.pde_problem_digest
    assert a.to_dict() == run_slice(VALUES, conditions=conditions(), mesh_size=MESH).to_dict()  # deterministic


@needs_gmsh
def test_face_temperatures_outside_the_material_data_are_out_of_domain_even_when_the_mean_is_inside():
    from forge_flagships.geometry_slice import domain_problem, run_slice

    hot_cold = conditions(hot=600, cold=100)  # mean 350 K inside, both faces outside 250-450 K
    assert domain_problem(hot_cold)
    r = run_slice(VALUES, conditions=hot_cold, mesh_size=MESH)
    validity = r.evaluation.result.validity["forge.slice.series_conduction_1d"]
    assert validity.status.value == "outside_validated_domain"


def test_campaign_is_deterministic_has_no_duplicate_model_rung_and_refuses_out_of_domain():
    from forge_flagships.geometry_slice import SLICE_LADDER, run_slice_campaign

    kw = dict(conditions=conditions(), height=Quantity(0.2, "m"), mesh_size=MESH, budget=3)
    run = run_slice_campaign(12, **kw)
    assert run.digest == run_slice_campaign(12, **kw).digest
    assert run.to_dict()["classification"] == "search_record_not_validation"
    assert [r.rung_id for r in SLICE_LADDER.rungs] == ["analytic", "numerical", "experimental"]
    providers_by_rank = {}
    for led in run.ledgers.values():
        for o in led.observations:
            providers_by_rank.setdefault(o.rank, set()).add(o.provider)
    assert all(providers_by_rank[a].isdisjoint(providers_by_rank[b]) for a in providers_by_rank for b in providers_by_rank if a < b)
    for standing, rank, why in run.standings().values():
        if standing == "supported":
            assert "supported is not validated" in why
    assert run_slice_campaign(12, **kw).context_digest != run_slice_campaign(12, **dict(kw, mesh_size=mm(20))).context_digest
    hot = run_slice_campaign(6, **dict(kw, conditions=conditions(hot=600, cold=100)))
    assert all(s == "undecided" for s, _, _ in hot.standings().values())
