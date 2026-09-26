"""FLAGSHIP B gates: real FEniCSx + CalculiX + Code_Aster through the BIG 12 runtime (WSL `fenicsx` env, process providers via FORGE_PROVIDER_ENVS)."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

from engcore.engineering import LevelStatus, committed_artifacts, verify_bundle, write_bundle
from engcore.system_runtime import Availability, NodeStatus, RunStatus, SystemExecutor, compare_runs, trace_result

try:
    from engcore.providers import default_registry
    import forge_fenicsx  # noqa: F401
    REG = default_registry()
    OK = all(REG.status(p).available for p in ("fenicsx", "calculix", "code_aster"))
except Exception:  # pragma: no cover
    OK = False
pytestmark = pytest.mark.skipif(not OK, reason="FEniCSx, CalculiX and Code_Aster are all required")

if OK:
    from forge_flagships import thermo_mechanical as tm


@pytest.fixture(scope="module")
def flagship():
    return tm.run_structure("flagship", REG, verification=True, study=True)


def obs(run, oid):
    o = run.result.observable(oid)
    assert o.availability is Availability.AVAILABLE, (oid, o.reason)
    return o.value.value.magnitude


def test_gate_b_real_thermal_and_three_structural_paths_execute_through_the_generic_runtime(flagship):
    r = flagship.result
    assert r.status is RunStatus.SUCCEEDED
    assert {p.provider_id for p in r.provider_records} == {"fenicsx", "calculix", "code_aster"}
    assert 350.5 < obs(flagship, "t_max") < 351.5 and obs(flagship, "t_min") == pytest.approx(303.15)
    # the thermal energy balance closes (a solver property, not a validation)
    assert obs(flagship, "heat_out") == pytest.approx(obs(flagship, "heat_in"), rel=1e-6)
    # mid-plate axial stress is the bar-theory value -E alpha (Tmean - Tref) for all three providers
    exact = tm.uniform_constrained_stress(tm.T_COLD + tm.FLUX * tm.LENGTH / (2 * tm.K_COND))
    for p in ("fenicsx", "calculix", "code_aster"):
        assert obs(flagship, f"sxx_mid_{p}") == pytest.approx(exact, rel=1e-3)
        assert 2.5e-5 < obs(flagship, f"disp_max_{p}") < 5e-5
    assert flagship.constraints and all(c.status == "satisfied" for c in flagship.constraints)


def test_independent_solvers_agree_within_the_predeclared_tolerance_and_it_is_corroboration_only(flagship):
    for a, b in (("fenicsx", "calculix"), ("fenicsx", "code_aster"), ("calculix", "code_aster")):
        assert obs(flagship, f"displacement_within_tolerance_{a}_{b}") == 1.0
        assert obs(flagship, f"max_abs_displacement_difference_{a}_{b}") < tm.DISP_AGREEMENT_TOL.magnitude
    assert obs(flagship, "max_abs_stress_difference_calculix_code_aster") < tm.STRESS_AGREEMENT_TOL.magnitude
    # the observed CalculiX difference is real and recorded (CalculiX expands plane-stress elements to 3-D wedges): non-zero, small
    assert 0 < obs(flagship, "max_abs_displacement_difference_fenicsx_calculix") < 1e-7
    l5 = flagship.ladder.entry(5)
    assert l5.status is LevelStatus.REACHED and all(e.classification == "solver_corroboration_not_validation" for e in l5.evidence)
    assert flagship.ladder.reference_level_reached == "none"                            # agreement is never validation


def test_exact_limits_are_reproduced_by_every_provider(flagship):
    for kind in ("free", "constrained"):
        v = flagship.verification[kind]
        assert v["status"] == "succeeded" and all(e is not None and e < 1e-9 for e in v["errors"].values()), v
    assert flagship.ladder.entry(3).status is LevelStatus.REACHED
    assert all(c.outcome == "met" for c in flagship.comparisons if c.reference_kind.value == "analytic_reference")


def test_the_predeclared_convergence_criterion_is_not_met_and_that_stays_visible(flagship):
    """Negative result kept: the mid-plate stress is converged to solver noise, so the predeclared 'observed order >= 0.9' criterion cannot be met for it."""
    study = flagship.study
    assert study["predeclared_criterion_met"] is False and "sxx_mid_fenicsx" in study["predeclared_failing"]
    assert study["post_hoc_noise_aware_met"] is True                                  # the post-hoc reading exists, is labelled, and never replaces the outcome
    l4 = flagship.ladder.entry(4)
    assert l4.status is LevelStatus.ATTEMPTED_NOT_REACHED
    assert {e.classification for e in l4.evidence} == {"discretisation_convergence", "post_hoc_discretisation_convergence"}
    # displacement converges at observed order ~2 for every provider
    for p in ("fenicsx", "calculix", "code_aster"):
        assert 1.9 < study["orders"][f"ux_mid_{p}"] < 2.1
    # the peak von Mises value converges slowly and is NOT claimed converged
    assert study["orders"]["vm_max_fenicsx"] < 1.0


def test_negative_control_a_load_that_leaves_the_property_range_is_refused_and_nothing_downstream_runs():
    run = tm.run_structure("over_range", REG)
    r = run.result
    assert r.receipt("thermal").status is NodeStatus.REFUSED and "property_range" in r.receipt("thermal").reason
    for p in ("fenicsx", "calculix", "code_aster"):
        assert r.receipt(f"struct_{p}").status is NodeStatus.BLOCKED
        assert r.observable(f"vm_max_{p}").value is None
    assert all(c.status == "unavailable" for c in run.constraints)                      # a missing result is never a pass
    assert run.summary.scientific_status == "insufficient_evidence"


def test_result_trace_reaches_the_provider_material_records_and_scenario(flagship):
    trace = trace_result(flagship.result, "sxx_mid_calculix")
    assert trace.complete, trace.gaps
    assert {"result", "node", "provider", "provider_execution", "material", "state", "system", "scenario", "timeline"} <= set(trace.levels())


def test_no_false_validation_the_credibility_status_stays_insufficient_evidence(flagship):
    assert flagship.summary.scientific_status == "insufficient_evidence"
    assert flagship.ladder.entry(6).status is LevelStatus.NOT_AVAILABLE and flagship.ladder.entry(7).status is LevelStatus.NOT_AVAILABLE
    assert "NOT QUANTIFIED" in flagship.summary.uncertainty.model_discrepancy
    assert flagship.result.trust_inputs.validation_evidence == ()


def test_gate_f_a_fresh_runtime_reproduces_the_run_and_the_bundle_verifies(flagship, tmp_path):
    again = tm.run_structure("flagship", REG)
    assert again.result.request_digest == flagship.result.request_digest and again.result.plan_digest == flagship.result.plan_digest
    cmp_ = compare_runs(flagship.result, again.result, rel_tol=1e-9)
    assert cmp_.identity_replay and cmp_.numerical_reproducibility and cmp_.scientific_validation == "not_assessed"
    d = str(tmp_path / "bundle")
    manifest = write_bundle(d, name="b", request=flagship.structure.request, result=flagship.result, summary=flagship.summary,
                            references=list({r.reference_id: r for r in flagship.references}.values()), artifacts=committed_artifacts(flagship.result, flagship.structure.exchange.files))
    assert verify_bundle(d).digest == manifest.digest
    vtus = [f for f, _ in manifest.files if f.endswith(".vtu")]
    assert len(vtus) == 4                                                                # temperature + one displacement/von Mises file per provider
    # the field files are byte-stable across runs (same content digest)
    assert {k: v for k, v in flagship.structure.exchange.files.items()} == {k: v for k, v in again.structure.exchange.files.items()}


def test_a_refused_request_carries_no_borrowed_verification_evidence_and_bundles_no_side_files(tmp_path):
    """Review findings H1/M9: verification evidence comes from OTHER requests; a run that did not itself succeed cannot claim it, and a refused node's field file is not bundled."""
    run = tm.run_structure("over_range", REG, verification=True, study=True)
    assert run.verification == {} and run.study == {}
    assert run.ladder.entry(3).status is LevelStatus.NOT_ATTEMPTED and run.ladder.entry(4).status is LevelStatus.NOT_ATTEMPTED
    assert run.ladder.entry(1).status is LevelStatus.REACHED and run.ladder.entry(2).status is not LevelStatus.REACHED
    assert run.structure.exchange.files and committed_artifacts(run.result, run.structure.exchange.files) == {}


def test_a_temperature_field_that_is_not_held_for_the_producing_execution_fails_the_structural_nodes_and_is_never_regenerated():
    st = tm.build_structure(tm.STRUCT_CASES["flagship"], REG)
    thermal = st.context.authorities._items["plate-thermal-fenicsx"]
    original = thermal._fn

    def thermal_then_lose_the_field(call):
        out = original(call)
        st.exchange.temperature.clear()                                                  # the field of THIS execution disappears
        return out

    thermal._fn = thermal_then_lose_the_field
    result = SystemExecutor(st.context).run(st.request)
    for p in ("fenicsx", "calculix", "code_aster"):
        assert result.receipt(f"struct_{p}").status is NodeStatus.FAILED and "not held" in result.receipt(f"struct_{p}").reason
    assert result.observable("vm_max_fenicsx").value is None


def test_the_request_identity_moves_with_every_declared_case_parameter():
    from dataclasses import replace
    base = tm.build_structure(tm.STRUCT_CASES["flagship"], REG).request
    for change in ({"flux": tm.FLUX * 1.5}, {"t_cold": tm.T_COLD + 5.0}, {"support": "free_roller"}):
        other = tm.build_structure(replace(tm.STRUCT_CASES["flagship"], **change), REG).request
        assert other.digest != base.digest, change
    same = tm.build_structure(tm.STRUCT_CASES["flagship"], REG).request
    assert same.digest == base.digest                                                    # and the same declaration is the same request
