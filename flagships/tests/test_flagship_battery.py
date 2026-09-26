"""FLAGSHIP A gates: real PyBaMM + TESPy through BIG 9 coupling, BIG 10 multi-timescale and the BIG 12 runtime (WSL `battery` env)."""

from __future__ import annotations

import json

import pytest

from engcore.engineering import BundleRefused, LevelStatus, committed_artifacts, verify_bundle, write_bundle
from engcore.system_runtime import Availability, NodeStatus, RunStatus, SystemExecutor, compare_runs, trace_result

try:
    from forge_flagships import battery_cooling as bc
    REG = bc.make_registry()
    OK = REG.status("pybamm").available and REG.status("tespy").available
except Exception:  # pragma: no cover
    OK = False
pytestmark = pytest.mark.skipif(not OK, reason="PyBaMM and TESPy are both required")


@pytest.fixture(scope="module")
def normal():
    return bc.run_flagship("normal", REG, refinement=True)


def o(run, oid):
    ob = run.result.observable(oid)
    assert ob.availability is Availability.AVAILABLE, (oid, ob.reason)
    return ob.value.value.magnitude


def test_gate_a_the_complete_pipeline_executes_with_real_providers_and_the_trace_is_intact(normal):
    r = normal.result
    assert r.status is RunStatus.SUCCEEDED, [(x.node_id, x.reason) for x in r.node_receipts if x.status is not NodeStatus.SUCCEEDED]
    assert {(p.provider_id, p.provider_version) for p in r.provider_records} == {("pybamm", REG.status("pybamm").version), ("tespy", REG.status("tespy").version)}
    assert o(normal, "represented_days") == pytest.approx(56.0) and o(normal, "resolved_days") == pytest.approx(4.0)   # 56 days represented, 4 resolved (14-day macro steps)
    trace = trace_result(r, "voltage_shift_degradation")
    assert trace.complete, trace.gaps
    assert {"provider", "provider_execution", "state", "material", "environment", "scenario", "timeline", "system"} <= set(trace.levels())
    assert normal.summary.trace_complete


def test_degradation_feeds_later_electrical_and_thermal_physics_and_is_separated_from_environment_drift(normal):
    fade = o(normal, "final_fade")
    assert 0.03 < fade < 0.08
    assert normal.result.final_state.owner("cell_slow").values[0].value.magnitude == pytest.approx(fade)   # the committed authoritative state is what later physics consumed
    deg, env = o(normal, "voltage_shift_degradation"), o(normal, "voltage_shift_environment")
    assert deg < -0.01 and abs(env) < abs(deg)                                        # the faded cell sits lower; the environment drift alone does not explain it
    assert o(normal, "min_soc_aged") < o(normal, "min_soc_control")                    # smaller usable capacity: the same charge swings SOC further
    assert o(normal, "peak_heat_shift_degradation") > 0                                # higher internal heat from the aged cell
    aged, control = normal.result.receipt("day_aged"), normal.result.receipt("day_control")
    assert aged.input_digests != control.input_digests                                 # different input identity (the fade), same window, same environment records


def test_conservation_and_the_first_law_check_close(normal):
    assert all(c.status == "closed" for c in normal.conservation) and len(normal.conservation) == 3
    assert normal.ladder.entry(2).status is LevelStatus.REACHED and normal.ladder.entry(3).status is LevelStatus.REACHED
    assert all(c.outcome == "met" for c in normal.comparisons) and normal.comparisons[0].reference_kind.value == "analytic_reference"


def test_window_refinement_meets_the_tolerances_but_not_the_monotone_requirement_so_level_4_is_not_reached(normal):
    """Negative result kept: the finest-pair differences are inside the tolerances, but they GROW as the coupling window shrinks
    (successive differences are not decreasing), so the study does not demonstrate convergence and level 4 is NOT reached.  Cause not investigated."""
    study = normal.study
    assert study["windows_s"] == [3600, 1800, 900]
    assert study["tolerances_met"] is True and study["monotone_met"] is False and study["met"] is False
    l4 = normal.ladder.entry(4)
    assert l4.status is LevelStatus.ATTEMPTED_NOT_REACHED and l4.evidence[0].outcome == "not_met"
    assert normal.ladder.verification_reached == 3
    q = study["quantities"]
    assert q["peak_cell_temperature"]["abs_difference_fine_pair"] < bc.REFINEMENT_TOL["peak_cell_temperature"].magnitude
    assert q["voltage_end_of_discharge"]["abs_difference_fine_pair"] < bc.REFINEMENT_TOL["voltage_end_of_discharge"].magnitude
    for name in ("peak_cell_temperature", "voltage_end_of_discharge", "peak_heat"):
        assert q[name]["abs_difference_fine_pair"] > q[name]["abs_difference_coarse_pair"]      # the differences grow with refinement
    assert "evidence from OTHER requests" in l4.note


def test_no_false_validation_no_second_provider_no_benchmark_and_the_nasa_dataset_is_not_compared(normal):
    assert normal.summary.scientific_status == "insufficient_evidence"
    for level in (5, 6, 7):
        assert normal.ladder.entry(level).status is LevelStatus.NOT_AVAILABLE
    assert normal.ladder.reference_level_reached == "none"
    (nasa, applic), = normal.references_considered
    assert nasa.kind.value == "experimental_dataset" and applic.status == "unknown"    # a reference with no applicable envelope is never compared
    assert "NOT QUANTIFIED" in normal.summary.uncertainty.model_discrepancy
    assert normal.result.trust_inputs.validation_evidence == ()


def test_constraint_assessments_of_the_normal_case_and_the_headline_summary(normal):
    assert {c.binding_id: c.status for c in normal.constraints} == {"b_fade": "satisfied", "b_soc_aged": "satisfied", "b_soc_fresh": "satisfied",
                                                                     "b_tmax_aged": "satisfied", "b_tmax_fresh": "satisfied"}
    text = normal.summary.render_text()
    assert "Voltage shift caused by degradation" in text and "UNKNOWN (" in text and "REFERENCE COMPARISONS" in text


def test_the_hot_case_violates_constraints_and_says_so():
    hot = bc.run_flagship("hot", REG, first_law=False)
    status = {c.binding_id: c.status for c in hot.constraints}
    assert hot.result.status is RunStatus.SUCCEEDED and status["b_tmax_fresh"] == "violated" and status["b_fade"] == "violated"
    assert o(hot, "final_fade") > 0.10 and o(hot, "peak_cell_temperature_fresh") > bc.TMAX_K


def test_negative_control_an_overload_the_cell_cannot_deliver_is_refused_by_the_provider_and_nothing_is_fabricated():
    run = bc.run_flagship("overload", REG, first_law=False)
    r = run.result
    assert r.receipt("day_fresh").status is NodeStatus.FAILED and "stopped early" in r.receipt("day_fresh").reason
    assert r.receipt("aging").status is NodeStatus.BLOCKED and r.receipt("shift").status is NodeStatus.BLOCKED
    assert r.observable("final_fade").value is None and r.observable("voltage_shift_degradation").value is None
    assert len(r.state_history) == 1                                                  # no state was committed
    assert all(c.status == "unavailable" for c in run.constraints)
    assert run.summary.scientific_status == "insufficient_evidence"


def test_negative_control_a_solved_day_outside_the_declared_soc_window_is_rolled_back():
    run = bc.run_flagship("outside_window", REG, first_law=False)
    r = run.result
    assert r.receipt("day_fresh").status is NodeStatus.REFUSED and "soc_window" in r.receipt("day_fresh").reason
    assert r.receipt("aging").status is NodeStatus.BLOCKED                             # the lifecycle run does not proceed from an inadmissible operating day
    assert r.observable("final_fade").value is None and len(r.state_history) == 1


def test_gate_f_serialize_fresh_runtime_replay_and_the_bundle_verifies(normal, tmp_path):
    from engcore.system_runtime import SystemRunResult
    wire = json.loads(json.dumps(normal.result.to_dict()))
    assert SystemRunResult.from_dict(wire).digest == normal.result.digest
    again = bc.run_flagship("normal", REG, first_law=False)
    assert again.result.request_digest == normal.result.request_digest and again.result.plan_digest == normal.result.plan_digest
    cmp_ = compare_runs(normal.result, again.result, rel_tol=1e-9)
    assert cmp_.identity_replay and cmp_.numerical_reproducibility and cmp_.scientific_validation == "not_assessed"
    d = str(tmp_path / "b")
    refs = list({r.reference_id: r for r in list(normal.references) + [x for x, _ in normal.references_considered]}.values())
    manifest = write_bundle(d, name="a", request=normal.flagship.request, result=normal.result, summary=normal.summary, references=refs, artifacts=committed_artifacts(normal.result, normal.flagship.store.files))
    assert verify_bundle(d).digest == manifest.digest
    assert {f for f, _ in manifest.files} >= {"artifacts/day-fresh_history.csv", "artifacts/day-aged_history.csv", "artifacts/day-control_history.csv"}


def test_a_refused_day_cannot_reach_the_analytic_level_with_default_arguments_and_its_side_files_are_never_bundled(tmp_path):
    """Review finding H1: the day's history table is written before its applicability is judged; a REFUSED day must not feed the first-law check or the bundle."""
    run = bc.run_flagship("outside_window", REG)                                       # default first_law=True, no special-casing
    assert run.result.receipt("day_fresh").status is NodeStatus.REFUSED
    assert run.ladder.entry(3).status is LevelStatus.NOT_ATTEMPTED and run.comparisons == ()
    assert "day-fresh_history.csv" in run.flagship.store.files                          # the side store DID receive the refused node's table ...
    assert committed_artifacts(run.result, run.flagship.store.files) == {}              # ... but no succeeded node references it
    with pytest.raises(BundleRefused, match="not referenced by any SUCCEEDED node"):
        write_bundle(str(tmp_path / "b"), name="x", request=run.flagship.request, result=run.result, summary=run.summary, artifacts=run.flagship.store.files)
    assert run.ladder.entry(1).status is LevelStatus.REACHED                          # the request itself was admissible; only the SOLVED state left applicability
