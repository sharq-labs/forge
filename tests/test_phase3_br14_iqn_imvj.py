"""Phase 3 BR14 -- one interface quasi-Newton accelerator: IQN-ILS (unchanged) and IQN-IMVJ.

IMVJ carries the inverse-Jacobian approximation of an accepted, converged
window into the next window of the same exact duration, layout and supports,
J = J_prev + (W - J_prev V)(D V)^+ D, and steps x <- H(x) - J r.  For a LINEAR
coupled map H(z) = A z + b, two independent secant pairs in 2D determine
M = A (A - I)^-1 on the whole space, and H(x) - M (H(x) - x) = -(A - I)^-1 b is
the fixed point for ANY x (derivation in the comments); that is what makes the
expectations below exact.  Acceleration never decides convergence: the runtime
still judges the unrelaxed transfer of every required edge.

NOT RUN (Phase 3 build phase): docs/work/DEFERRED_VALIDATION.md, DV-69..DV-72.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.acceleration import InterfaceQuasiNewton
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.execution.multiphysics.relaxation import RelaxationController
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, RelaxationKind, RelaxationPolicy,
    TimePolicy, WindowOutcome,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

DIGEST = "0" * 64
ONE = Fraction(1)


def _imvj(columns=3, factor=0.5, dimension=16, reuse=10):
    return RelaxationPolicy(RelaxationKind.IQN_IMVJ, factor, 0.05, 1.0, columns, 1e-10, dimension, reuse)


def _ils(columns=3, factor=0.5):
    return RelaxationPolicy(RelaxationKind.IQN_ILS, factor, 0.05, 1.0, columns)


# ---- the policy record ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("dimension,reuse", [(0, 5), (5, 0), (4097, 5), (5, 1001), (True, 5)])
def test_imvj_bounds_are_declared_and_never_defaulted(dimension, reuse):
    with pytest.raises(InvalidScientificProblem):
        RelaxationPolicy(RelaxationKind.IQN_IMVJ, 0.5, 0.05, 1.0, 3, 1e-10, dimension, reuse)


def test_imvj_fields_on_another_kind_are_refused():
    with pytest.raises(InvalidScientificProblem, match="IQN-IMVJ relaxation only"):
        RelaxationPolicy(RelaxationKind.IQN_ILS, 0.5, 0.05, 1.0, 3, 1e-10, 16, 0)


def test_imvj_policy_round_trips_and_ils_keeps_its_serialized_form():
    assert RelaxationPolicy.from_dict(_imvj().to_dict()) == _imvj()
    assert "imvj_max_dimension" not in _ils().to_dict()
    assert set(_ils().to_dict()) == {"schema", "kind", "factor", "minimum_factor", "maximum_factor", "iqn_columns", "iqn_filter"}


def test_no_gauss_seidel_iqn_variant_is_admitted():
    time = TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s"))
    criteria = (ConvergenceCriterion("e_x", 0.0, Quantity(1e-8, "K")),)
    with pytest.raises(InvalidScientificProblem, match="Jacobi"):
        CouplingPlan("p", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL, time, ("a", "b"), criteria, _imvj(), 10, True)


# ---- the accelerator ---------------------------------------------------------------------------------------------

LAYOUT = (("e_x", 1), ("e_y", 1))
SUPPORTS = (("e_x", "scalar"), ("e_y", "scalar"))


def _h(z, offset=-300.0):
    """H(x, y) = (2 y + offset, x); fixed point x = y = -offset."""
    return np.array([2.0 * z[1] + offset, z[0]])


def _iterate(acc, z, steps, offset=-300.0):
    out = []
    for _ in range(steps):
        z = acc.step(LAYOUT, SUPPORTS, z, _h(z, offset))
        out.append(z.copy())
    return out


def test_without_a_carried_approximation_imvj_takes_exactly_the_ils_steps():
    ils, imvj = InterfaceQuasiNewton(_ils()), InterfaceQuasiNewton(_imvj())
    ils.begin_window(0, ONE)
    imvj.begin_window(0, ONE)
    a = _iterate(ils, np.array([290.0, 290.0]), 3)
    b = _iterate(imvj, np.array([290.0, 290.0]), 3)
    for left, right in zip(a, b):
        assert left == pytest.approx(right, abs=1e-9)
    # the ERT V1 hand-computed path: (285, 290) -> (280, 288) -> (300, 300)
    assert a[-1] == pytest.approx([300.0, 300.0])


def test_a_carried_approximation_jumps_to_the_new_fixed_point_on_the_first_step():
    # window 0 learns M = A (A - I)^-1 from two independent secant pairs; in window 1 the offset is -320
    # (fixed point 320) and the first step H(x) - M r lands on it from an arbitrary start
    acc = InterfaceQuasiNewton(_imvj())
    acc.begin_window(0, ONE)
    _iterate(acc, np.array([290.0, 290.0]), 3)
    acc.end_window(accepted=True, converged=True)
    acc.begin_window(1, ONE)
    first = acc.step(LAYOUT, SUPPORTS, np.array([280.0, 310.0]), _h(np.array([280.0, 310.0]), -320.0))
    assert first == pytest.approx([320.0, 320.0], abs=1e-9)
    assert any(e["action"] == "imvj_reused" for e in acc.events)


@pytest.mark.parametrize("change,reason", [
    ("duration", "duration"),
    ("rejected", "rejected"),
    ("not_converged", "did not converge"),
    ("unknown_duration", "unknown exact duration"),
])
def test_a_carried_approximation_is_discarded_and_the_reason_recorded(change, reason):
    acc = InterfaceQuasiNewton(_imvj())
    acc.begin_window(0, ONE)
    _iterate(acc, np.array([290.0, 290.0]), 3)
    acc.end_window(accepted=change != "rejected", converged=change != "not_converged", reason="test rollback")
    acc.begin_window(1, None if change == "unknown_duration" else Fraction(1, 2) if change == "duration" else ONE)
    first = acc.step(LAYOUT, SUPPORTS, np.array([280.0, 310.0]), _h(np.array([280.0, 310.0]), -320.0))
    # a fresh first step is constant relaxation: x + 0.5 (H(x) - x) = (280 + 0.5*20, 310 - 0.5*30)
    assert first == pytest.approx([290.0, 295.0])
    discarded = [e for e in acc.events if e["action"] == "imvj_discarded"]
    assert discarded and reason in discarded[-1]["reason"]


def test_the_reuse_bound_restarts_the_approximation():
    acc = InterfaceQuasiNewton(_imvj(reuse=1))
    for window in range(3):
        acc.begin_window(window, ONE)
        _iterate(acc, np.array([290.0, 290.0]), 3, offset=-300.0 - window)
        acc.end_window(accepted=True, converged=True)
    actions = [e["action"] for e in acc.events]
    # window 1 reuses the window-0 approximation; window 2 must restart (one reuse allowed)
    assert actions.count("imvj_reused") == 1 and "imvj_discarded" in actions
    assert "restart" in [e for e in acc.events if e["action"] == "imvj_discarded"][0]["reason"]


def test_a_changed_layout_or_support_never_reuses_secant_information():
    acc = InterfaceQuasiNewton(_imvj())
    acc.begin_window(0, ONE)
    _iterate(acc, np.array([290.0, 290.0]), 3)
    acc.end_window(accepted=True, converged=True)
    acc.begin_window(1, ONE)
    other = (("e_x", "scalar"), ("e_y", "meshfingerprint", "cell", 1))
    acc.step(LAYOUT, other, np.array([280.0, 310.0]), _h(np.array([280.0, 310.0])))
    assert "supports" in [e for e in acc.events if e["action"] == "imvj_discarded"][-1]["reason"]
    with pytest.raises(InvalidScientificProblem, match="support"):
        acc.step(LAYOUT, SUPPORTS, np.array([280.0, 310.0]), _h(np.array([280.0, 310.0])))


def test_an_interface_above_the_declared_dimension_is_refused():
    acc = InterfaceQuasiNewton(_imvj(dimension=1))
    acc.begin_window(0, ONE)
    with pytest.raises(InvalidScientificProblem, match="imvj_max_dimension"):
        acc.step(LAYOUT, SUPPORTS, np.array([1.0, 2.0]), np.array([2.0, 3.0]))


def test_a_non_finite_carried_step_falls_back_and_discards_the_approximation():
    acc = InterfaceQuasiNewton(_imvj())
    acc.begin_window(0, ONE)
    _iterate(acc, np.array([290.0, 290.0]), 3)
    acc.end_window(accepted=True, converged=True)
    acc._carried = np.full((2, 2), np.inf)  # white box: an approximation that is no longer admissible
    acc.begin_window(1, ONE)
    first = acc.step(LAYOUT, SUPPORTS, np.array([280.0, 310.0]), _h(np.array([280.0, 310.0])))
    assert np.all(np.isfinite(first)) and first == pytest.approx([280.0 + 0.5 * 40.0, 310.0 - 0.5 * 30.0])
    assert acc._carried is None
    assert any(e["action"] == "fallback_constant" for e in acc.events)


def test_imvj_uncertainty_is_unknown():
    store = InMemoryBulkStore()
    controller = RelaxationController(_imvj(), BulkDataResolver(store), store, {})
    sigma = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.5, "K"), source="declared",
                        method="declared sigma")
    assert controller.propagate_uncertainty(sigma, sigma, factor=None, unit="K", edge_id="e").kind is UncertaintyKind.UNKNOWN


# ---- runtime -----------------------------------------------------------------------------------------------------


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _participant(spec, fn, initial):
    out = spec.outputs[0].port_id
    unknown = Uncertainty.unknown("test")

    def advance(request):
        value = fn(dict(request.inputs), request.end.magnitude_in("s"))
        return AdvanceResult(request.end, {out: value}, {out: unknown}, 1, True)

    return CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({out: initial}, {out: unknown}), advance=advance,
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, DIGEST, True), None),
        restore=lambda cp: None)


def _runtime(relaxation, windows=3):
    """x = 2 y - 300 - 10 t_end, y = x: the fixed point moves every window; the operator does not."""
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    pa = _participant(a, lambda i, t: Quantity(2.0 * i["y"].magnitude_in("K") - 300.0 - 10.0 * t, "K"), Quantity(290.0, "K"))
    pb = _participant(b, lambda i, t: Quantity(i["x"].magnitude_in("K"), "K"), Quantity(290.0, "K"))
    graph = PhysicsGraph("imvj", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                          CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("imvj", CouplingScheme.IMPLICIT, IterationSemantics.JACOBI,
                        TimePolicy(Quantity(0, "s"), Quantity(windows, "s"), Quantity(1, "s")), (),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-8, "K")),
                         ConvergenceCriterion("e_y", 0.0, Quantity(1e-8, "K"))),
                        relaxation, 50, True)
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store)


def _run(runtime):
    unknown = Uncertainty.unknown("test initial coupling value")
    return runtime.run("imvj", external_inputs={},
                       initial_coupling_values={"e_x": Quantity(290.0, "K"), "e_y": Quantity(290.0, "K")},
                       initial_coupling_uncertainty={"e_x": unknown, "e_y": unknown})


def test_imvj_reuses_the_learned_operator_in_later_windows_and_records_it():
    ils = _run(_runtime(_ils()))
    imvj = _run(_runtime(_imvj()))
    assert all(w.outcome is WindowOutcome.CONVERGED for w in ils.windows + imvj.windows)
    # window 0 is identical arithmetic; later windows: iteration 1 jumps to the moved fixed point, iteration 2 confirms
    assert len(imvj.windows[0].iterations) == len(ils.windows[0].iterations)
    assert all(len(w.iterations) == 2 for w in imvj.windows[1:])
    assert all(len(w.iterations) > 2 for w in ils.windows[1:])
    # fixed point of the last window (t_end = 3): x = 2x - 330 -> 330 K
    assert imvj.final_outputs["a.x"]["magnitude"] == pytest.approx(330.0, abs=1e-6)
    record = imvj.final_outputs["_acceleration"]
    assert record["policy"]["kind"] == "iqn_imvj" and any(e["action"] == "imvj_reused" for e in record["events"])
    assert "_acceleration" not in ils.final_outputs  # routine IQN-ILS runs keep their identity


def test_a_second_run_of_one_runtime_starts_without_acceleration_history():
    runtime = _runtime(_imvj())
    first, second = _run(runtime), _run(runtime)
    assert [len(w.iterations) for w in first.windows] == [len(w.iterations) for w in second.windows]
    assert first.final_outputs == second.final_outputs


# ---- 2026-10-18 remediation E4-2: an event re-run drops the outer attempt's staged approximation, on the record ----


def test_an_event_aligned_re_run_logs_the_staged_approximation_it_drops():
    # window 0, no carried approximation: two Jacobi steps give two residuals, so IMVJ stages a J (white box);
    # the runtime then restores and re-runs the window to an event (begin_window(index, None)) WITHOUT closing
    # the outer attempt -- that staged J is dropped and must be recorded like end_window's drops are
    acc = InterfaceQuasiNewton(_imvj())
    acc.begin_window(0, ONE)
    _iterate(acc, np.array([290.0, 290.0]), 2)
    assert acc._staged is not None and acc._carried is None
    acc.begin_window(0, None)
    discarded = [e for e in acc.events if e["action"] == "imvj_discarded"]
    assert len(discarded) == 1 and "unknown exact duration" in discarded[0]["reason"]
    assert acc._staged is None and acc._carried is None


def test_a_nested_begin_with_nothing_staged_or_carried_logs_nothing():
    acc = InterfaceQuasiNewton(_imvj())
    acc.begin_window(0, ONE)
    acc.begin_window(0, None)
    assert not [e for e in acc.events if e["action"] == "imvj_discarded"]


# ---- 2026-10-18 remediation E4-3 / E4-4: runtime failure recovery -----------------------------------------------


def _recording(log, participant_id, *, fail=False):
    def finalize():
        log.append(participant_id)
        if fail:
            raise RuntimeError(f"{participant_id} finalize failed")
    return finalize


def test_one_failing_finalize_does_not_skip_the_others_and_is_reported():
    from engcore.execution.multiphysics.runtime import MultiphysicsExecutionError

    runtime, log = _runtime(_ils()), []
    runtime.participants["a"].finalize = _recording(log, "a", fail=True)  # sorted first: it used to stop the loop
    runtime.participants["b"].finalize = _recording(log, "b")
    with pytest.raises(MultiphysicsExecutionError, match="participant finalize failed: a: RuntimeError"):
        _run(runtime)
    assert log == ["a", "b"]


def test_a_failing_finalize_never_replaces_the_window_s_own_exception():
    class Boom(Exception):
        pass

    def exploding(inputs, t):
        raise Boom("participant b failed to advance")

    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    pa = _participant(a, lambda i, t: Quantity(2.0 * i["y"].magnitude_in("K") - 300.0, "K"), Quantity(290.0, "K"))
    pb = _participant(b, exploding, Quantity(290.0, "K"))
    graph = PhysicsGraph("boom", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                          CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("boom", CouplingScheme.IMPLICIT, IterationSemantics.JACOBI,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), (),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-8, "K")),
                         ConvergenceCriterion("e_y", 0.0, Quantity(1e-8, "K"))), _ils(), 50, True)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store)
    log = []
    runtime.participants["a"].finalize = _recording(log, "a", fail=True)
    runtime.participants["b"].finalize = _recording(log, "b")
    with pytest.raises(Exception) as caught:
        _run(runtime)
    chain, item = [], caught.value
    while item is not None:
        chain.append(item)
        item = item.__cause__ or item.__context__
    assert any(isinstance(item, Boom) for item in chain)  # the advance failure is what propagates
    assert "a finalize failed" not in str(caught.value)
    assert any("participant finalize also failed: a: RuntimeError" in note
               for note in getattr(caught.value, "__notes__", ()))
    assert log == ["a", "b"]


@pytest.mark.parametrize("kwargs", [
    {"run_id": "   "},
    {"initial_state": {"nobody": {}}},
    {"scenario_digest": "not-a-digest"},
], ids=["blank_run_id", "unknown_state_owner", "malformed_scenario_digest"])
def test_a_refusal_before_any_participant_call_leaves_the_runtime_usable(kwargs):
    runtime = _runtime(_ils())
    unknown = Uncertainty.unknown("test initial coupling value")
    arguments = dict(run_id="imvj", external_inputs={},
                     initial_coupling_values={"e_x": Quantity(290.0, "K"), "e_y": Quantity(290.0, "K")},
                     initial_coupling_uncertainty={"e_x": unknown, "e_y": unknown})
    arguments.update(kwargs)
    run_id = arguments.pop("run_id")
    with pytest.raises(InvalidScientificProblem):
        runtime.run(run_id, **arguments)
    record = _run(runtime)  # the participants were never called, so nothing was retired
    assert all(w.outcome is WindowOutcome.CONVERGED for w in record.windows)


def test_a_refusal_after_participant_code_ran_still_retires_the_runtime():
    from engcore.execution.multiphysics.runtime import MultiphysicsExecutionError

    runtime = _runtime(_ils())
    unknown = Uncertainty.unknown("test initial coupling value")
    with pytest.raises(InvalidScientificProblem, match="unknown edges"):
        runtime.run("imvj", external_inputs={},
                    initial_coupling_values={"e_x": Quantity(290.0, "K"), "e_y": Quantity(290.0, "K"),
                                             "e_nowhere": Quantity(1.0, "K")},
                    initial_coupling_uncertainty={"e_x": unknown, "e_y": unknown})
    with pytest.raises(MultiphysicsExecutionError, match="unusable"):
        _run(runtime)


def test_a_run_started_from_inside_a_running_run_is_refused_and_retires_the_runtime():
    # review MINOR-1: a nested run refused in the exempt prefix used to reset the outer run's fail-closed flag
    from engcore.execution.multiphysics.runtime import MultiphysicsExecutionError

    holder, nested = {}, []

    def reentrant(inputs, t):
        try:
            holder["runtime"].run("   ", external_inputs={})
        except Exception as exc:  # a participant that swallows the nested failure
            nested.append(exc)
        return Quantity(inputs["x"].magnitude_in("K"), "K")

    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    pa = _participant(a, lambda i, t: Quantity(2.0 * i["y"].magnitude_in("K") - 300.0, "K"), Quantity(290.0, "K"))
    pb = _participant(b, reentrant, Quantity(290.0, "K"))
    graph = PhysicsGraph("nested", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                            CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("nested", CouplingScheme.IMPLICIT, IterationSemantics.JACOBI,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), (),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-8, "K")),
                         ConvergenceCriterion("e_y", 0.0, Quantity(1e-8, "K"))), _ils(), 50, True)
    store = InMemoryBulkStore()
    holder["runtime"] = runtime = MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb},
                                                      resolver=BulkDataResolver(store), store=store)
    # the swallowed nested call still retired the runtime, so the outer run cannot complete; which check stops it
    # (the runtime's own, or a retired participant's) is not what this asserts
    with pytest.raises((MultiphysicsExecutionError, InvalidScientificProblem)):
        _run(runtime)
    assert nested and isinstance(nested[0], MultiphysicsExecutionError)
    assert "inside a running one" in str(nested[0])
    with pytest.raises(MultiphysicsExecutionError, match="unusable"):
        _run(runtime)
