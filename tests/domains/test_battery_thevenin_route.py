"""battery.thevenin_1rc execution route (Rock A): verification against independent references, and hostile cases.

Independent references used here, none of which shares arithmetic with the exact zero-order-hold march:
* a high-accuracy adaptive ODE integration (scipy DOP853, rtol 1e-12) of dz/dt and dv_p/dt with a tabulated OCV;
* the production Rint kernel (``solver.evaluate_step``), which the 1RC route must reduce to as R1 -> 0;
* analytic limits: pure rest relaxation, tau << dt (steady branch), tau >> dt (capacitor integration).
Verification is not validation: nothing here says the model describes a real cell.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from engcore.domains.battery import context as ctx
from engcore.domains.battery import thevenin_route as tr
from engcore.domains.battery.cell import CellSpecification, DischargeLoad
from engcore.domains.battery.solver import evaluate_step
from engcore.domains.battery.thevenin import Thevenin1RCParameters
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.curves import DeclaredCurve, TabulatedForm
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.results.uncertainty import UncertaintyKind
from engcore.scientific.units.quantity import Quantity as Q

OCV_TABLE = ((0.0, 3.0), (0.1, 3.45), (0.3, 3.62), (0.6, 3.85), (0.9, 4.08), (1.0, 4.2))


def _cell(curve: bool = True, r0: float = 0.05) -> CellSpecification:
    kwargs = dict(cell_id="fx-18650", nominal_capacity=Q(2.0, "ampere_hour"), internal_resistance=Q(r0, "ohm"),
                  coulombic_efficiency=Q(0.99, "dimensionless"))
    if curve:
        kwargs["open_circuit_voltage_curve"] = DeclaredCurve(
            quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless", unit="volt",
            lower=0.0, upper=1.0, form=TabulatedForm(OCV_TABLE))
    else:
        kwargs.update(open_circuit_voltage_at_full=Q(4.2, "volt"), open_circuit_voltage_at_empty=Q(3.0, "volt"))
    return CellSpecification(**kwargs)


def _set(r1: float = 0.03, c1: float = 2000.0, curve: bool = True, r0: float = 0.05, imax: float = 4.0,
         set_id: str = "fx-set") -> tr.Thevenin1RCParameterSet:
    return tr.Thevenin1RCParameterSet(set_id, _cell(curve, r0), Thevenin1RCParameters(Q(r1, "ohm"), Q(c1, "farad")),
                                      Q(283.15, "kelvin"), Q(313.15, "kelvin"), Q(imax, "ampere"),
                                      "declared verification fixture; not identified from any measurement")


def _init(z0: float = 0.9, vp0: float = 0.0, basis: str = "rested > 5 tau before t0") -> tr.Thevenin1RCInitialState:
    return tr.Thevenin1RCInitialState(Q(z0, "dimensionless"), Q(vp0, "volt"), basis)


def _profile(segments=((300, 2.0), (120, 0.0), (60, 3.5), (600, 0.0)), temp: float = 298.15,
             convention: str = tr.POSITIVE_DISCHARGE, profile_id: str = "pulse-rest") -> tr.DischargeRestProfile:
    return tr.DischargeRestProfile(profile_id, tuple(tr.ProfileSegment(Q(d, "second"), Q(i, "ampere"),
                                                                       Q(temp, "kelvin")) for d, i in segments),
                                   convention)


# ---- verification against independent references ---------------------------------------------------------------------
def test_the_march_agrees_with_an_independent_adaptive_ode_integration():
    ps, init, prof = _set(), _init(), _profile()
    run = tr.run_thevenin_1rc(ps, init, prof)
    r0, r1, tau, q_as, eta = 0.05, 0.03, 0.03 * 2000.0, 2.0 * 3600.0, 0.99
    xs, ys = zip(*OCV_TABLE)
    z, vp, t0, worst = 0.9, 0.0, 0.0, 0.0
    for (duration, current), point in zip(((300, 2.0), (120, 0.0), (60, 3.5), (600, 0.0)), run.trajectory):
        sol = solve_ivp(lambda t, y: [-current / (eta * q_as), (current * r1 - y[1]) / tau], (t0, t0 + duration),
                        [z, vp], method="DOP853", rtol=1e-12, atol=1e-14)
        z, vp = sol.y[0, -1], sol.y[1, -1]
        t0 += duration
        v_ref = float(np.interp(z, xs, ys)) - current * r0 - vp
        worst = max(worst, abs(point.terminal_voltage_v - v_ref), abs(point.state_of_charge - z),
                    abs(point.polarization_voltage_v - vp))
    assert worst < 1e-9


def test_splitting_an_interval_changes_nothing_because_the_update_is_exact():
    one = tr.run_thevenin_1rc(_set(), _init(), _profile(((600, 2.0),))).trajectory[-1]
    many = tr.run_thevenin_1rc(_set(), _init(), _profile(tuple((6, 2.0) for _ in range(100)))).trajectory[-1]
    assert abs(one.polarization_voltage_v - many.polarization_voltage_v) < 1e-12
    assert abs(one.terminal_voltage_v - many.terminal_voltage_v) < 1e-12


def test_rest_relaxes_exponentially_and_leaves_soc_alone():
    run = tr.run_thevenin_1rc(_set(), _init(z0=0.5, vp0=0.08), _profile(((90, 0.0),)))
    end = run.trajectory[-1]
    assert end.state_of_charge == 0.5
    assert end.polarization_voltage_v == pytest.approx(0.08 * math.exp(-90 / 60.0), rel=1e-12)
    assert end.terminal_voltage_v == pytest.approx(end.open_circuit_voltage_v - end.polarization_voltage_v, rel=1e-12)


def test_as_r1_vanishes_the_route_reduces_to_the_production_rint_kernel():
    ps = _set(r1=1e-12, c1=1.0, curve=False)
    end = tr.run_thevenin_1rc(ps, _init(z0=0.8), _profile(((600, 1.5),))).trajectory[-1]
    rint = evaluate_step(_cell(curve=False), DischargeLoad(load_id="l", current=Q(1.5, "ampere"),
                                                            initial_state_of_charge=Q(0.8, "dimensionless"),
                                                            cell_temperature=Q(298.15, "kelvin"),
                                                            duration=Q(600, "second")))
    assert end.state_of_charge == pytest.approx(rint.final_state_of_charge, abs=1e-15)
    assert end.terminal_voltage_v == pytest.approx(rint.terminal_voltage, abs=1e-11)


def test_a_time_constant_much_shorter_than_the_interval_gives_the_steady_branch_voltage():
    end = tr.run_thevenin_1rc(_set(c1=1.0), _init(), _profile(((60, 2.0),))).trajectory[-1]   # tau = 0.03 s
    assert end.polarization_voltage_v == pytest.approx(2.0 * 0.03, rel=1e-15)


def test_a_time_constant_much_longer_than_the_interval_integrates_like_a_capacitor():
    end = tr.run_thevenin_1rc(_set(r1=0.03, c1=1e6), _init(vp0=0.01), _profile(((10, 2.0),))).trajectory[-1]
    tau = 0.03 * 1e6
    expected = 0.01 + (2.0 * 10 / 1e6) - 0.01 * 10 / tau          # first order in dt/tau
    assert end.polarization_voltage_v == pytest.approx(expected, rel=1e-6)


def test_every_check_passes_and_only_the_dimension_check_claims_a_level():
    result = tr.run_thevenin_1rc(_set(), _init(), _profile()).result
    checks = {c.name: c for c in result.validation.checks}
    assert {c.outcome.value for c in checks.values()} == {"pass"}
    assert [n for n, c in checks.items() if c.establishes is not None] == [tr.CHECK_METRIC_DIMENSIONS]


def test_the_superposition_check_detects_a_wrong_polarization_update(monkeypatch):
    real = tr.evaluate_thevenin_step

    def drifting(cell, parameters, state, *, current, duration):
        out = real(cell, parameters, state, current=current, duration=duration)
        bumped = tr.TheveninState(out.final_state.state_of_charge,
                                  Q(out.final_state.polarization_voltage.magnitude * 1.001, "volt"))
        return type(out)(**{**out.__dict__, "final_state": bumped})
    monkeypatch.setattr(tr, "evaluate_thevenin_step", drifting)
    checks = {c.name: c for c in tr.run_thevenin_1rc(_set(), _init(), _profile()).result.validation.checks}
    assert checks[tr.CHECK_POLARIZATION_SUPERPOSITION].outcome.value == "fail"


# ---- result, provenance, replay ---------------------------------------------------------------------------------------
def test_the_result_is_attributed_to_the_execution_with_explicit_unknown_uncertainty():
    ps, prof = _set(), _profile()
    result = tr.run_thevenin_1rc(ps, _init(), prof).result
    (binding,) = result.provenance.bindings
    assert (binding.model.model_id, binding.realization.realization_id, binding.solver.solver_id) == (
        tr.MODEL_ID, tr.REALIZATION_ID, tr.SOLVER_ID)
    assert result.provenance.metadata["parameter_set_sha256"] == ps.digest
    assert result.provenance.metadata["profile_sha256"] == prof.digest
    assert result.provenance.metadata["sign_convention"] == tr.POSITIVE_DISCHARGE
    assert {u.kind for u in result.uncertainty.values()} == {UncertaintyKind.UNKNOWN}
    assert set(result.uncertainty) == set(result.values)
    assert result.validity[tr.MODEL_ID].status is ValidityStatus.IN_DOMAIN


def test_a_replay_record_reproduces_bit_for_bit_after_a_json_round_trip():
    run = tr.run_thevenin_1rc(_set(), _init(), _profile())
    again = tr.replay_thevenin_1rc(json.loads(json.dumps(run.replay.to_dict())))
    assert again.replay.payload["trajectory"] == run.replay.payload["trajectory"]
    assert again.result.provenance.metadata["replay_record_sha256"] == run.replay.digest


def _record():
    return tr.run_thevenin_1rc(_set(), _init(), _profile()).replay.to_dict()


def _redigest(record):
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return {**body, "record_sha256": tr._sha256(body)}


def test_a_stale_replay_record_is_refused_not_rerun_under_new_code():
    record = _record()
    record["model"] = {"model_id": tr.MODEL_ID, "version": "0.0.9"}
    with pytest.raises(tr.ReplayRefused, match="stale"):
        tr.replay_thevenin_1rc(_redigest(record))


def test_an_altered_replay_record_is_refused():
    record = _record()
    record["trajectory"][0][-1] += 1e-6
    with pytest.raises(tr.ReplayRefused, match="digest"):
        tr.replay_thevenin_1rc(record)


def test_a_forged_trajectory_with_a_recomputed_digest_does_not_reproduce():
    record = _record()
    record["trajectory"][0][-1] += 1e-6
    with pytest.raises(tr.ReplayRefused, match="reproduce"):
        tr.replay_thevenin_1rc(_redigest(record))


def test_a_changed_parameter_set_under_its_old_digest_is_refused():
    record = _record()
    record["parameter_set"]["polarization_resistance"]["magnitude"] = 0.031
    with pytest.raises(tr.ReplayRefused, match="parameter set"):
        tr.replay_thevenin_1rc(_redigest(record))


# ---- hostile inputs ---------------------------------------------------------------------------------------------------
def test_wrong_current_sign_is_refused_both_ways():
    with pytest.raises(InvalidScientificProblem, match="charge"):
        _profile(((60, -1.0),))
    with pytest.raises(InvalidScientificProblem, match="positive_discharge"):
        _profile(convention="negative_discharge")


def test_invalid_soc_is_refused_and_never_clipped():
    with pytest.raises(InvalidScientificProblem):
        _init(z0=1.2)
    with pytest.raises(InvalidScientificProblem, match="interval 0.*not clipping|interval 0.*clipping"):
        tr.run_thevenin_1rc(_set(), _init(z0=0.05), _profile(((3600, 2.0),)))


def test_missing_initial_state_evidence_is_refused():
    with pytest.raises(InvalidScientificProblem, match="basis"):
        _init(basis="  ")
    with pytest.raises(InvalidScientificProblem, match="neither is defaulted"):
        tr.Thevenin1RCInitialState(Q(0.9, "dimensionless"), None, "rested")


def test_temperature_outside_the_parameter_sets_range_is_reported_outside_the_domain():
    result = tr.run_thevenin_1rc(_set(), _init(), _profile(temp=273.15)).result
    assert result.validity[tr.MODEL_ID].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_current_above_the_declared_maximum_is_reported_outside_the_domain():
    result = tr.run_thevenin_1rc(_set(imax=3.0), _init(), _profile()).result
    assert result.validity[tr.MODEL_ID].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_a_parameter_set_without_a_basis_or_with_an_inverted_range_is_refused():
    with pytest.raises(InvalidScientificProblem, match="basis"):
        tr.Thevenin1RCParameterSet("s", _cell(), Thevenin1RCParameters(Q(0.03, "ohm"), Q(2000.0, "farad")),
                                   Q(283.15, "kelvin"), Q(313.15, "kelvin"), Q(4.0, "ampere"), "")
    with pytest.raises(InvalidScientificProblem, match="maximum > minimum"):
        tr.Thevenin1RCParameterSet("s", _cell(), Thevenin1RCParameters(Q(0.03, "ohm"), Q(2000.0, "farad")),
                                   Q(313.15, "kelvin"), Q(283.15, "kelvin"), Q(4.0, "ampere"), "fixture")


def test_a_problem_for_another_parameter_set_is_refused_by_the_solver():
    ps, other, init, prof = _set(), _set(r1=0.04, set_id="other"), _init(), _profile()
    solver = tr.Thevenin1RCSolver()
    problem = tr.build_thevenin_problem(other, init, prof)
    solver.bind(ps, init, prof, problem.problem_id)
    with pytest.raises(InvalidScientificProblem, match="another parameter set"):
        solver.prepare(problem)


def test_the_route_is_not_registered_as_a_production_battery_model():
    from engcore.domains.battery.models import BATTERY_MODELS
    from engcore.domainpacks import builtin_battery

    assert tr.MODEL_ID not in {m.model_id for m in BATTERY_MODELS}
    assert "thevenin" not in repr(builtin_battery.__dict__.get("PACK_ID", ""))
    assert tr.THEVENIN_1RC_MODEL.validation_status.value == "self_consistent"


def test_swapped_arguments_are_refused_with_a_scientific_error_not_a_crash():
    with pytest.raises(InvalidScientificProblem, match="must be a Thevenin1RCParameterSet"):
        tr.run_thevenin_1rc(_init(), _set(), _profile())


def test_an_incomplete_replay_record_is_refused_not_a_key_error():
    record = _record()
    del record["initial_state"]
    with pytest.raises(tr.ReplayRefused):
        tr.replay_thevenin_1rc(_redigest(record))
