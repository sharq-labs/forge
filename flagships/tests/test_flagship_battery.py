"""FLAGSHIP A gates: real PyBaMM + TESPy through BIG 9 coupling, BIG 10 multi-timescale and the BIG 12 runtime (WSL `battery` env)."""

from __future__ import annotations

import json

import pytest

from engcore.engineering import BundleRefused, LevelStatus, committed_artifacts, verify_bundle, write_bundle
from engcore.system_runtime import Availability, NodeStatus, RunStatus, SystemExecutor, compare_runs, trace_result

# Import and registry construction are NOT guarded: a defect there must fail, not read as
# 'provider unavailable'. Only the availability answers decide the skip (BIG 14 review finding 6).
from forge_flagships import battery_cooling as bc
REG = bc.make_registry()
OK = REG.status("pybamm").available and REG.status("tespy").available
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
    for level in (5, 6):
        assert normal.ladder.entry(level).status is LevelStatus.NOT_AVAILABLE
    l7 = normal.ladder.entry(7)                                                        # BIG 14: the cell model met measured data, in-sample, and missed
    assert l7.status is LevelStatus.ATTEMPTED_NOT_REACHED and len(l7.evidence) == 1
    link = l7.evidence[0]
    assert link.outcome == "not_met" and link.classification == "cell_model_in_sample_consistency_not_validation"
    assert "in-sample" in link.record["data_classification"] and "not this module" in link.record["scope"]
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


def test_the_cell_balance_comes_only_from_the_pinned_dfn_record():
    """BIG 14: the DFN cell's two active-material factors come from the committed big14-a-lgm50-dfn record, pinned by digest,
    under its pre-registered decision rule; the lab heat-transfer coefficient is never carried."""
    rec = bc.cell_model_study()["record"]
    assert bc.MODEL == "DFN" and bc.CELL_OPTIONS == {"heat of mixing": "true"}
    assert rec["decision_for_flagship"]["flagship_carries_balance"] is True and rec["decision_for_flagship"]["flagship_carries_h"] is False
    assert bc.cell_balance() == (rec["step_1"]["factors"]["negative"], rec["step_1"]["factors"]["positive"])
    assert bc.CELL_STUDY_SHA256 == "95e3792be09be593d0876e3ef4808e970f64d2eefcb8a790eb54149a18d5378f"
    assert bc.CELL_STUDY_PREREGISTRATION_SHA256 == "e2fa1c2cafb86318a04996a0fea26d22fdd897c4461fe3fa3d061b1776485fe2"


def _tampered(tmp_path, monkeypatch, edit):
    """Write an edited copy of the record and pin THAT copy's digest, so only the re-derivation can refuse it."""
    import copy
    import hashlib
    import json
    rec = copy.deepcopy(bc.cell_model_study()["record"])
    edit(rec)
    raw = json.dumps(rec, indent=1, sort_keys=True).encode("utf-8")
    path = tmp_path / "record.json"
    path.write_bytes(raw)
    monkeypatch.setattr(bc, "CELL_STUDY", str(path))
    monkeypatch.setattr(bc, "CELL_STUDY_SHA256", hashlib.sha256(raw).hexdigest())


def test_an_edited_record_is_refused_by_its_pinned_digest(tmp_path, monkeypatch):
    path = tmp_path / "record.json"
    path.write_bytes(open(bc.CELL_STUDY, "rb").read().replace(b"0.853898705996209", b"0.853898705996208"))
    monkeypatch.setattr(bc, "CELL_STUDY", str(path))
    with pytest.raises(ValueError, match="not the pinned one"):
        bc.cell_balance()


@pytest.mark.parametrize("edit", [
    # a failed identification (factor at the registered bound) presented as carried
    lambda r: (r["step_1"]["factors"].update(positive=0.70), r["decision_for_flagship"]["flagship_factors"].update(positive=0.70)),
    # carried factors that are not the identified ones
    lambda r: r["decision_for_flagship"]["flagship_factors"].update(negative=1.0),
    # the lab heat-transfer coefficient carried into the flagship
    lambda r: r["decision_for_flagship"].update(flagship_carries_h=True),
    # a better model-form band than the table shows
    lambda r: r["decision_for_flagship"]["model_form_band_C2"].update(v_rmse_mV=[1.0, 2.0]),
    # an outcome that does not follow from the table
    lambda r: r["judgement"].update(met=True),
    lambda r: r["judgement"]["cell02"].update(T1=True),
    # a table edited to pass, with the stated judgement left as NOT MET
    lambda r: r["table"]["DFN"]["cell02"]["C/2"].update(rise_err_K=0.0),
    # a record bound to another registration
    lambda r: r.update(preregistration_sha256="0" * 64),
], ids=["at-bound-carried", "factors-differ", "h-carried", "band-improved", "met-flipped", "T1-flipped", "table-edited", "other-registration"])
def test_a_record_whose_outcome_or_decision_does_not_follow_from_its_data_is_refused(tmp_path, monkeypatch, edit):
    _tampered(tmp_path, monkeypatch, edit)
    with pytest.raises(ValueError):
        bc.cell_balance()


def test_the_level_7_note_and_report_text_are_derived_from_the_record():
    text = bc.cell_outcome_text()
    assert text.startswith("NOT MET") and "surface-temperature rise missed on cell02, cell04" in text
