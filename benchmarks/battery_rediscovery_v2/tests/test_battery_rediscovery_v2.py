"""battery_rediscovery_v2: candidate-side mechanics, scoring and the conclusion rule, on synthetic data only.

No test here reads real data or a candidate output; the real run happens once, through ``launch``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import pathlib

import numpy as np
import pytest

from benchmarks.battery_rediscovery_v2.candidate import arms, common
from benchmarks.battery_rediscovery_v2.candidate.families import build_families
from benchmarks.battery_rediscovery_v2.candidate.views import v1_problem
from benchmarks.battery_rediscovery_v2.evaluator import conclusion as cr
from benchmarks.battery_rediscovery_v2.evaluator import score
from benchmarks.battery_rediscovery_v2.tests import synthetic_pack as syn
from engcore.mind.repsem import RoleRefused, RoleTable, assess, bind, legacy_role_table
from engcore.mind.repsem.families import bind_trajectory

ROOT = pathlib.Path(__file__).resolve().parents[3]
V2 = ROOT / "benchmarks" / "battery_rediscovery_v2"


# ---- families ------------------------------------------------------------------------------------------------------
def _loop(t, i, z0, q, r0, r1, c1, ocv):
    z, v1, out = [z0], [0.0], []
    for k in range(1, len(t)):
        dt = t[k] - t[k - 1]
        z.append(z[-1] - i[k] * dt / q)
        a = math.exp(-dt / (r1 * c1))
        v1.append(a * v1[-1] + r1 * (1 - a) * i[k])
    return np.array([ocv(zk) - ik * r0 - vk for zk, ik, vk in zip(z, i, v1)])


def test_measured_family_matches_a_direct_loop_on_nonuniform_sampling():
    spec = syn.s2()
    fam = build_families(0)["rc1_measured_ocv/1"]
    roles = RoleTable.from_spec(spec)
    b = bind(fam, roles, spec["clock"])
    traj = copy.deepcopy(spec["sets"]["calibration"][0])
    t = np.asarray(traj["columns"]["t_s"])
    traj["columns"]["t_s"] = list(t + np.r_[0.0, np.cumsum(np.linspace(0, 0.03, len(t) - 1))])   # non-uniform
    bt = bind_trajectory(fam, b, roles, traj)
    knots = np.asarray(spec["declared_family"]["constants"]["ocv_knots"])
    y, states = fam.simulate({"R0": 0.02, "R1": 0.015, "C1": 1700.0}, bt, spec["declared_family"]["constants"])
    ref = _loop(bt.clock, bt.slots["driver"], traj["initial_state"]["soc"], traj["conditions"]["capacity_As"], 0.02,
                0.015, 1700.0, lambda z: np.interp(z, knots[:, 0], knots[:, 1]))
    assert np.max(np.abs(y - ref)) < 1e-12
    assert set(states) == {"charge_state"}


def test_fitted_family_reads_its_knot_values_as_latent_parameters():
    fam = build_families(len(common.FITTED_OCV_KNOTS_SOC))["rc1_fitted_ocv/1"]
    assert fam.parameters[:3] == ("R0", "R1", "C1")
    assert fam.parameters[3:] == tuple(f"ocv_k{k}" for k in range(len(common.FITTED_OCV_KNOTS_SOC)))
    spec = syn.s1()
    roles = RoleTable.from_spec(spec)
    b = bind(fam, roles, spec["clock"])
    assert b.slots == {"driver": "current_A", "charge_state": "soc"}


def test_families_bind_by_role_not_by_name():
    spec = syn.s2()
    renamed = json.loads(json.dumps(spec).replace('"current_A"', '"load"'))
    fam = build_families(0)["rc1_measured_ocv/1"]
    b = bind(fam, RoleTable.from_spec(renamed), renamed["clock"])
    assert b.slots["driver"] == "load"
    with pytest.raises(Exception):
        bind(fam, legacy_role_table(spec), spec["clock"])


def test_a_role_table_missing_a_column_is_refused():
    spec = syn.s2()
    spec["variables"] = [v for v in spec["variables"] if v["name"] != "level_A"]
    with pytest.raises(RoleRefused):
        RoleTable.from_spec(spec)


# ---- the v1 view ---------------------------------------------------------------------------------------------------
def test_v1_view_picks_columns_by_role_and_copies_declarations():
    spec = syn.s2()
    renamed = json.loads(json.dumps(spec).replace('"temperature_C"', '"cell_temp"'))
    p = v1_problem(renamed)
    cal = p.calibration()
    assert np.allclose(cal[0].temperature, spec["sets"]["calibration"][0]["columns"]["temperature_C"])
    assert p.voltage_sigma() == pytest.approx(0.005 / 3 ** 0.5)
    assert p.ocv_knots is not None
    assert p.acceptance("within_cell_heldout", "pulses_alternate_soc") == {"rmse_mV_max": 15.0, "p95_abs_mV_max": 30.0}
    assert p.rest_band == 0.075
    p1 = v1_problem(syn.s1())
    assert p1.ocv_knots is None and p1.voltage_sigma() is None
    assert p1.model["ocv"]["knots_soc"] == list(common.FITTED_OCV_KNOTS_SOC)


# ---- arms (fast paths only; the fitted-OCV combined arm is exercised by the dry run) -------------------------------
@pytest.mark.parametrize("arm", ["OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES",
                                 "CAREFUL_BASELINE", "FIXED_FIT", "ALWAYS_FIT", "ALWAYS_REFUSE"])
def test_every_arm_answers_every_axis_on_the_measured_ocv_problem(arm):
    rec = arms.RUN[arm](syn.s2())
    assert set(rec["answers"]) == set(common.AXES)
    assert all(v["disposition"] in common.DISPOSITIONS for v in rec["answers"].values())
    assert rec["answers"]["CROSS_CELL_TRANSFER"]["disposition"] in common.NON_COMMITTAL or arm == "ALWAYS_FIT"


def test_representation_only_is_refused_at_binding_under_legacy_roles():
    rec = arms.representation_only(syn.s1())
    for axis in ("MODEL_ADEQUACY", "IDENTIFIABILITY", "MODEL_DISCREPANCY"):
        assert rec["answers"][axis]["disposition"] == "REFUSED"
        assert rec["answers"][axis]["refusal_reason"] == "REPRESENTATION_UNAVAILABLE"


def test_roles_arm_without_a_measured_ocv_drops_the_state_covariate():
    p = v1_problem(syn.s1())
    pool = arms._roles_pool(p.calibration(), p.rest_band, p.ocv_knots)
    assert pool.settable == ("t_on_s", "I_A") and pool.covariates == ("T_K",) and pool.unit == "V"


def test_combined_arm_is_deterministic_and_replays_exactly():
    from engcore.mind.repsem import replay
    spec = syn.s2()
    a, b = arms.combined(spec), arms.combined(spec)
    assert common.digest(a) == common.digest(b)
    assert replay(json.loads(json.dumps(a["assessment"])), spec, arms.families_for(spec))["status"] == "EXACT"


def test_unknown_noise_never_becomes_a_number():
    spec = syn.s2()
    spec["measurement_noise"] = {"sigma": None, "independent": None, "status": "UNKNOWN", "basis": "test"}
    rec = arms.combined(spec)
    assert rec["answers"]["MODEL_DISCREPANCY"]["disposition"] in common.NON_COMMITTAL
    assert rec["answers"]["IDENTIFIABILITY"]["disposition"] != "SUPPORTED"


# ---- scoring and the conclusion rule ------------------------------------------------------------------------------
@pytest.mark.parametrize("answer,truth,want", [
    ("SUPPORTED", "SUPPORTED", "CORRECT"), ("NOT_SUPPORTED", "SUPPORTED", "FALSE_REJECT"),
    ("REVIEW", "SUPPORTED", "FALSE_REFUSE"), ("SUPPORTED", "NOT_SUPPORTED", "FALSE_SUPPORT"),
    ("NOT_ASSESSABLE", "NOT_ASSESSABLE", "CORRECT_REFUSAL"), ("SUPPORTED", "NOT_ASSESSABLE", "FALSE_SUPPORT"),
    ("NOT_SUPPORTED", "NOT_ASSESSABLE", "UNSUPPORTED_DECISION"), ("REFUSED", None, "UNSCORED")])
def test_outcome_mapping(answer, truth, want):
    assert score.outcome(answer, truth) == want


def _fake(answers: dict[str, dict[str, str]], truth: dict[str, dict[str, str | None]]):
    specs = {pid: {"sets": {"within_unit_heldout": {"x": [1]}, "cross_unit_heldout": {"x": [1]}}} for pid in truth}
    out = {}
    for arm, per in answers.items():
        outputs = {pid: {"answers": {a: {"disposition": per[pid][a]} for a in score.AXES}} for pid in truth}
        out[arm] = score.score_arm(outputs, {pid: {a: {"truth": t} for a, t in tv.items()} for pid, tv in truth.items()},
                                   specs)
    return out


TRUTH = {"P": {"MODEL_ADEQUACY": "SUPPORTED", "IDENTIFIABILITY": "SUPPORTED", "WITHIN_CELL_GENERALIZATION": "NOT_SUPPORTED",
               "CROSS_CELL_TRANSFER": "SUPPORTED", "MODEL_DISCREPANCY": "NOT_ASSESSABLE"}}
REFUSE_ALL = {"P": {a: "NOT_ASSESSABLE" for a in score.AXES}}
RIGHT = {"P": {a: (t if t != "NOT_ASSESSABLE" else "NOT_ASSESSABLE") for a, t in TRUTH["P"].items()}}


def _claims(disp: str = "SUPPORTED", reason: str | None = None, cond: dict | None = None):
    ref = None if reason is None else {"reason": reason, "condition": cond or {}}
    return {"P": {a: {"disposition": disp, "refusal": ref} for a in score.AXES}}


def test_conclusion_confirmed_when_combined_is_right_and_others_refuse():
    s = _fake({"OLD_MIND": REFUSE_ALL, "REPRESENTATION_ONLY": REFUSE_ALL, "SEMANTIC_ROLES_ONLY": REFUSE_ALL,
               "REPRESENTATION_PLUS_ROLES": RIGHT, "CAREFUL_BASELINE": RIGHT}, TRUTH)
    c = cr.conclude(seal_ok=True, leakage_ok=True, replay_exact=True, scores=s, combined_claims=_claims())
    assert c["verdict"] == "REAL_DATA_IMPROVEMENT_CONFIRMED", c


def test_conclusion_leakage_and_replay_gates_come_first():
    s = _fake({a: RIGHT for a in ("OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES",
                                  "CAREFUL_BASELINE")}, TRUTH)
    assert cr.conclude(seal_ok=True, leakage_ok=False, replay_exact=True, scores=s, combined_claims=_claims())["verdict"] \
        == "LEAKAGE_INVALIDATED"
    assert cr.conclude(seal_ok=True, leakage_ok=True, replay_exact=False, scores=s, combined_claims=_claims())["verdict"] \
        == "INCONCLUSIVE"


def test_conclusion_attributes_representation_refusals():
    s = _fake({a: REFUSE_ALL for a in ("OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES",
                                       "CAREFUL_BASELINE")}, TRUTH)
    rep = cr.conclude(seal_ok=True, leakage_ok=True, replay_exact=True, scores=s,
                      combined_claims=_claims("REFUSED", "REPRESENTATION_UNAVAILABLE", {"family": "x"}))
    assert rep["verdict"] == "REPRESENTATION_STILL_LIMITING"
    roles = cr.conclude(seal_ok=True, leakage_ok=True, replay_exact=True, scores=s,
                        combined_claims=_claims("REFUSED", "REPRESENTATION_UNAVAILABLE", {"slot": "driver"}))
    assert roles["verdict"] == "SEMANTIC_ROLES_STILL_LIMITING"
    other = cr.conclude(seal_ok=True, leakage_ok=True, replay_exact=True, scores=s,
                        combined_claims=_claims("NOT_ASSESSABLE", "INSUFFICIENT_EVIDENCE"))
    assert other["verdict"] == "NO_REAL_DATA_IMPROVEMENT"


def test_conclusion_partial_when_false_support_does_not_rise():
    half = {"P": dict(REFUSE_ALL["P"], MODEL_ADEQUACY="SUPPORTED", IDENTIFIABILITY="SUPPORTED")}
    s = _fake({"OLD_MIND": REFUSE_ALL, "REPRESENTATION_ONLY": half, "SEMANTIC_ROLES_ONLY": REFUSE_ALL,
               "REPRESENTATION_PLUS_ROLES": half, "CAREFUL_BASELINE": RIGHT}, TRUTH)
    c = cr.conclude(seal_ok=True, leakage_ok=True, replay_exact=True, scores=s, combined_claims=_claims())
    assert c["verdict"] == "PARTIAL_REAL_DATA_IMPROVEMENT", c
    assert c["hypotheses"]["H1"]["holds"] and not c["hypotheses"]["H2"]["holds"]


# ---- frozen history is untouched ----------------------------------------------------------------------------------
def test_battery_v1_frozen_files_are_untouched():
    plan = json.loads((ROOT / "benchmarks" / "battery_rediscovery_v1" / "PLAN.json").read_bytes())
    bad = [p for p, sha in plan["frozen_files"].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != sha]
    assert bad == []


def test_pack_manifest_binds_the_pack_files():
    problems = common.load_pack()
    assert sorted(problems) == ["Q1", "Q2"]
    for spec in problems.values():
        RoleTable.from_spec(spec)                              # every column has a declared role
        assert spec["declared_family"]["family_id"] in arms.families_for(spec)


# ---- runtime audit negative controls ------------------------------------------------------------------------------
def test_runtime_audit_flags_reads_of_outputs_history_and_evaluator_modules(tmp_path):
    from benchmarks.battery_rediscovery_v2 import leakage as lk
    out = tmp_path / "out"
    out.mkdir()
    ok = {"opened": [[str(out / "A__Q1.json"), "wb"], [str(V2 / "candidate" / "pack" / "Q1.json"), "rb"],
                     [str(ROOT / "benchmarks" / "battery_rediscovery_v1" / "candidate" / "__pycache__" /
                          "model.cpython-314.pyc"), "rb"]],
          "modules": ["benchmarks.battery_rediscovery_v2.candidate.arms"], "exit": 0}
    r = lk.runtime_findings(ok, [out])
    assert not (r["paths_outside_roots"] or r["outputs_read_during_run"] or r["forbidden_modules"])
    bad = {"opened": ok["opened"] + [[str(out / "CAREFUL_BASELINE__Q1.json"), "rb"],
                                     [str(ROOT / "benchmarks" / "battery_rediscovery_v1" / "results" / "EVALUATION.json"), "rb"],
                                     [str(ROOT / "benchmarks" / "battery_rediscovery_v1" / "candidate" / "pack" / "P2.json"), "rb"]],
           "modules": ok["modules"] + ["benchmarks.battery_rediscovery_v2.evaluator.reference",
                                       "benchmarks.mind_repsem_v1.gap_map"], "exit": 0}
    r = lk.runtime_findings(bad, [out])
    assert len(r["outputs_read_during_run"]) == 1
    assert len(r["paths_outside_roots"]) == 2
    assert r["forbidden_modules"] == ["benchmarks.battery_rediscovery_v2.evaluator.reference",
                                      "benchmarks.mind_repsem_v1.gap_map"]
