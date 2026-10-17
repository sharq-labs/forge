"""Interface quasi-Newton (IQN-ILS) coupling acceleration (Engineering Runtime V1, Big Rock 2).

Joint over the interface vector of every edge, Jacobi coupling only, history
reset every window.  Convergence is still judged on the UNRELAXED transfer.
The update is not a scalar mix, so no scalar factor is recorded and the
propagated uncertainty is UNKNOWN.  NOT YET EXECUTED (build phase): see
docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingWindowNotConverged, InitializationResult, MultiphysicsRuntime,
)
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

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")
DIGEST = "0" * 64


def _sigma(value=0.5):
    return Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(value, "K"), source="declared",
                       method="declared sigma")


def _iqn(columns=3, factor=0.5):
    return RelaxationPolicy(RelaxationKind.IQN_ILS, factor, 0.05, 1.0, columns)


def _constant(factor=0.5):
    return RelaxationPolicy(RelaxationKind.CONSTANT, factor, 0.05, 1.0)


# ---- the policy record ---------------------------------------------------------------------


@pytest.mark.parametrize("columns", [0, 51, -1, True])
def test_iqn_requires_a_bounded_history(columns):
    with pytest.raises(InvalidScientificProblem):
        RelaxationPolicy(RelaxationKind.IQN_ILS, 0.5, 0.05, 1.0, columns)


@pytest.mark.parametrize("kind", [RelaxationKind.CONSTANT, RelaxationKind.AITKEN])
def test_history_columns_on_another_kind_are_refused(kind):
    with pytest.raises(InvalidScientificProblem, match="IQN-ILS relaxation only"):
        RelaxationPolicy(kind, 0.5, 0.05, 1.0, 3)


def test_existing_relaxation_policies_keep_their_serialized_identity():
    for policy in (RelaxationPolicy(), _constant(), RelaxationPolicy(RelaxationKind.AITKEN, 0.5, 0.05, 1.0)):
        assert "iqn_columns" not in policy.to_dict()
        assert RelaxationPolicy.from_dict(policy.to_dict()) == policy


def test_iqn_policy_round_trips():
    assert RelaxationPolicy.from_dict(_iqn(4).to_dict()) == _iqn(4)


def _plan(semantics, relaxation):
    return CouplingPlan("p", CouplingScheme.IMPLICIT, semantics, TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
                        ("a", "b"), (ConvergenceCriterion("e_x", 0.0, Quantity(1e-8, "K")),), relaxation, 10, True)


def test_iqn_with_serial_gauss_seidel_coupling_is_refused():
    with pytest.raises(InvalidScientificProblem, match="Jacobi"):
        _plan(IterationSemantics.SERIAL, _iqn())
    _plan(IterationSemantics.JACOBI, _iqn())  # admitted


# ---- controller ----------------------------------------------------------------------------


def _controller(policy):
    store = InMemoryBulkStore()
    return RelaxationController(policy, BulkDataResolver(store), store, {})


def _k(value, unit="K"):
    return Quantity(value, unit)


def _step(controller, x, y, *, y_unit="K"):
    """One joint step on H(x, y) = (2y - 300, x); y may be carried in another unit."""
    y_k = y.magnitude_in("K")
    raw_x = _k(2 * y_k - 300)
    raw_y = _k(x.magnitude_in("K")).to(y_unit)
    out = controller.relax_joint({"e_x": (x, raw_x, "K"), "e_y": (y, raw_y, y_unit)})
    return out["e_x"], out["e_y"]


def test_scalar_relax_is_refused_under_iqn():
    with pytest.raises(InvalidScientificProblem, match="joint interface vector"):
        _controller(_iqn()).relax("e", _k(0), _k(1), unit="K")


def test_relax_joint_is_refused_for_scalar_mix_policies():
    with pytest.raises(InvalidScientificProblem, match="IQN-ILS update only"):
        _controller(_constant()).relax_joint({"e": (_k(0), _k(1), "K")})


def test_joint_iqn_reaches_the_linear_fixed_point_on_the_third_update():
    # hand-computed: z0 = (290, 290) -> fallback (285, 290) -> weighted secant (280, 288) -> (300, 300)
    # (edge scales: e_x 10 K from r0 = -10 K; e_y 5 K from its first non-zero residual r1 = -5 K; the third
    # update is exact for a linear map once two independent secant pairs span the 2-D interface)
    controller = _controller(_iqn(columns=3, factor=0.5))
    x, y = _k(290), _k(290)
    x, y = _step(controller, x, y)
    assert (x.magnitude_in("K"), y.magnitude_in("K")) == pytest.approx((285.0, 290.0))
    x, y = _step(controller, x, y)
    assert (x.magnitude_in("K"), y.magnitude_in("K")) == pytest.approx((280.0, 288.0))
    x, y = _step(controller, x, y)
    assert (x.magnitude_in("K"), y.magnitude_in("K")) == pytest.approx((300.0, 300.0))


def test_joint_iqn_step_does_not_depend_on_the_unit_an_edge_is_declared_in():
    in_k, in_mk = _controller(_iqn()), _controller(_iqn())
    xa, ya = _k(290), _k(290)
    xb, yb = _k(290), _k(290000, "mK")
    for _ in range(3):
        xa, ya = _step(in_k, xa, ya)
        xb, yb = _step(in_mk, xb, yb, y_unit="mK")
        assert xa.magnitude_in("K") == pytest.approx(xb.magnitude_in("K"))
        assert ya.magnitude_in("K") == pytest.approx(yb.magnitude_in("K"))


def test_joint_iqn_history_does_not_survive_a_window_reset():
    controller = _controller(_iqn())
    x, y = _step(controller, _k(290), _k(290))
    _step(controller, x, y)
    controller.reset_window()
    x, y = _step(controller, _k(290), _k(290))
    assert (x.magnitude_in("K"), y.magnitude_in("K")) == pytest.approx((285.0, 290.0))  # a fresh first step


def test_joint_iqn_refuses_an_interface_that_changes_inside_a_window():
    controller = _controller(_iqn())
    controller.relax_joint({"e_x": (_k(0), _k(1), "K")})
    with pytest.raises(InvalidScientificProblem, match="layout changed"):
        controller.relax_joint({"e_x": (_k(0), _k(1), "K"), "e_y": (_k(0), _k(1), "K")})


def test_iqn_uncertainty_is_unknown_never_a_scalar_mix():
    out = _controller(_iqn()).propagate_uncertainty(_sigma(), _sigma(), factor=None, unit="K", edge_id="e")
    assert out.kind is UncertaintyKind.UNKNOWN


def test_constant_relaxation_still_propagates_declared_uncertainty():
    out = _controller(_constant()).propagate_uncertainty(_sigma(), _sigma(), factor=0.5, unit="K", edge_id="e")
    assert out.kind is UncertaintyKind.STANDARD


# ---- runtime (Jacobi) ----------------------------------------------------------------------


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _stateless(spec, fn, initial):
    out = spec.outputs[0].port_id

    def advance(request):
        return AdvanceResult(request.end, {out: fn(dict(request.inputs))}, {out: _sigma()}, 1, True)

    return CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({out: initial}, {out: _sigma()}), advance=advance,
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, DIGEST, True), None),
        restore=lambda cp: None)


def _fixed_point(relaxation, *, gain, offset, start, max_iterations=50):
    """Jacobi: x = gain * y + offset, y = x."""
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    pa = _stateless(a, lambda i: Quantity(gain * i["y"].magnitude_in("K") + offset, "K"), Quantity(start, "K"))
    pb = _stateless(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"), Quantity(start, "K"))
    graph = PhysicsGraph("iqn", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                         CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("iqn", CouplingScheme.IMPLICIT, IterationSemantics.JACOBI,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), (),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-8, "K")), ConvergenceCriterion("e_y", 0.0, Quantity(1e-8, "K"))),
                        relaxation, max_iterations, True)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store)
    return runtime, start


def _run(made):
    runtime, start = made
    return runtime.run("iqn", external_inputs={},
                       initial_coupling_values={"e_x": Quantity(start, "K"), "e_y": Quantity(start, "K")},
                       initial_coupling_uncertainty={"e_x": _sigma(), "e_y": _sigma()})


def test_iqn_converges_an_expanding_coupling_that_constant_relaxation_cannot():
    # x = 2y - 300 with y = x: Jacobi with constant 0.5 has spectral radius ~1.21 and diverges; the fixed point is 300 K
    with pytest.raises(CouplingWindowNotConverged):
        # 8 iterations: the error grows ~1.21x per iteration, to ~45 K -- non-convergent, still physical (> 0 K)
        _run(_fixed_point(_constant(), gain=2.0, offset=-300.0, start=290.0, max_iterations=8))
    run = _run(_fixed_point(_iqn(), gain=2.0, offset=-300.0, start=290.0))
    window = run.windows[0]
    assert window.outcome is WindowOutcome.CONVERGED
    assert run.final_outputs["a.x"]["magnitude"] == pytest.approx(300.0, abs=1e-6)
    # IQN records no invented scalar factor
    assert all(dict(iteration.relaxation_factors) == {} for iteration in window.iterations)


def test_iqn_needs_fewer_iterations_than_constant_relaxation_on_a_contracting_coupling():
    # x = 0.9y + 5, fixed point 50 K; Jacobi with constant 0.5 contracts at ~0.97 per iteration
    constant = _run(_fixed_point(_constant(), gain=0.9, offset=5.0, start=40.0, max_iterations=2000))
    iqn = _run(_fixed_point(_iqn(), gain=0.9, offset=5.0, start=40.0))
    assert iqn.final_outputs["a.x"]["magnitude"] == pytest.approx(50.0, abs=1e-6)
    assert len(iqn.windows[0].iterations) < len(constant.windows[0].iterations)


def test_iqn_edge_uncertainty_is_unknown_where_constant_relaxation_propagates_it():
    constant = _run(_fixed_point(_constant(), gain=0.9, offset=5.0, start=40.0, max_iterations=2000))
    iqn = _run(_fixed_point(_iqn(), gain=0.9, offset=5.0, start=40.0))
    for edge_id in ("e_x", "e_y"):
        assert constant.final_outputs["_edge_uncertainty"][edge_id]["kind"] == "standard"
        assert iqn.final_outputs["_edge_uncertainty"][edge_id]["kind"] == "unknown"
