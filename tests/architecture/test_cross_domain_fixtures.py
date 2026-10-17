"""Cross-domain architectural fixtures (CDAR, docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md).

DESIGN PROBES, NOT DOMAIN SUPPORT.  Three tiny non-thermal systems run on the SHARED coupling structure
(``MultiphysicsRuntime``, ``CallbackParticipant``, ``PhysicsGraph``, ``CoupledConservation``) to show whether that
structure carries thermal assumptions.  They model nothing a user should rely on; their results are design findings,
never evidence for electrical, mechanical or chemical capability.  Participants are built here from the generic
``CallbackParticipant``; no product code is added.

* RC circuit -- voltage (a potential) and current (a flow) as distinct ports; a time state.
* Spring-mass -- force and displacement (scalar, along one axis); motion.  Frames are probed only at the record level.
* Chemical mixing -- concentration-driven exchange and a REQUIRED species balance.

Each fixture has two kinds of test:
* an expectation of what the generic structure already does, derived by hand in the comments (closed form);
* a GAP PIN (``test_gap_...``) that asserts the gap as it stands today, citing the audit row (gaps A-1..A-13 of
  docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md, which lands with the OD-6 branch).  It goes red the day the gap is
  closed, and must then be rewritten as the requirement's own test.  Gap pins are ordinary tests, not ``xfail``: an
  xfail is reported as a skip of type ``pytest.xfail``, which hardened recertification refuses as an UNEXPECTED_SKIP
  (tools/certification/skip_admission.py).

Time steps are binary-exact (1/16 s, 1/32 s, 1/2 s) so the window count, and with it the closed-form exponent, is
fixed.

NOT RUN (build-first; written 2026-10-18).  They must run once before any of the program gates M1-E3 is decided.
The program contract and the audit cited here land with the OD-6 branch (feat/od6-engineering-program-epic).
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.execution.multiphysics.runtime import require_conservation
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    BalanceSide, CheckpointRecord, ConservationTermBinding, ConvergenceCriterion, CouplingEdge, CouplingPlan,
    CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef,
    RelaxationPolicy, TimePolicy, TransferMeasure, WindowOutcome,
)
from engcore.scientific.multiphysics.conservation import CoupledConservation
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("architectural fixture: output uncertainty not modelled")


# ---- shared helpers ------------------------------------------------------------------------------------------------


def _port(port_id, direction, quantity, unit):
    return PortDefinition(port_id, PortDirection(direction), PortKind.SCALAR, quantity, unit)


def _spec(pid, ports):
    return ParticipantSpec(pid, f"fixture.{pid}", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _participant(spec, state, outputs_of, step):
    """A stateful, restorable callback participant.

    ``outputs_of(state) -> {port: (magnitude, unit)}`` gives the initial outputs; ``step(state, inputs, dt)`` advances
    ``state`` in place over one window and returns the outputs at the window end.
    """

    def quantities(values):
        return {name: Quantity(magnitude, unit) for name, (magnitude, unit) in values.items()}

    def initialize(_instant, _inputs, _uncertainty):
        values = quantities(outputs_of(state))
        return InitializationResult(values, {name: UNKNOWN for name in values})

    def advance(request):
        dt = request.end.magnitude_in("s") - request.start.magnitude_in("s")
        values = quantities(step(state, dict(request.inputs), dt))
        return AdvanceResult(request.end, values, {name: UNKNOWN for name in values}, 1, True)

    def checkpoint(instant):
        digest = hashlib.sha256(repr(sorted(state.items())).encode()).hexdigest()
        return RuntimeCheckpoint(CheckpointRecord(spec.participant_id, instant, digest, True), dict(state))

    def restore(saved):
        state.clear()
        state.update(saved.token)

    return CallbackParticipant(spec, initialize=initialize, advance=advance, checkpoint=checkpoint, restore=restore)


def _explicit(plan_id, order, window_s, windows):
    return CouplingPlan(plan_id, CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(window_s * windows, "s"), Quantity(window_s, "s")), order)


def _run(graph, plan, participants, run_id):
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store)
    return runtime.run(run_id, external_inputs={})


def _value(run, key):
    return run.final_outputs[key]["magnitude"]


# ==== 1. Electrical RC circuit ======================================================================================
#
# resistor: i = (Vs - v_c) / R                         capacitor (state v_c): dv_c/dt = i / C
# Serial explicit order (resistor, capacitor): the v_c edge is lagged (the resistor reads v_k, the capacitor's output at
# the window start) and the i edge is forward.  i is held over the window (zero-order input hold), so the capacitor's
# update v <- v + i dt / C is exact for that i, and
#     v_{k+1} = v_k + (Vs - v_k) dt / (R C)   =>   v_N = Vs - (Vs - v_0) (1 - dt / (R C))^N      (closed form)
# The last current was computed from v_{N-1}:  i_N = (Vs - v_0) (1 - dt / (R C))^(N-1) / R.

VS, R, C, V0 = 5.0, 1000.0, 1e-3, 0.0          # V, ohm, F, V   (RC = 1 s)
RC_DT, RC_N = 1 / 16, 32                       # 2 s, dt / RC = 0.0625


def _rc_specs():
    resistor = _spec("resistor", [_port("v_c", "input", "electric_potential", "V"),
                                  _port("i", "output", "electric_current", "A")])
    capacitor = _spec("capacitor", [_port("i", "input", "electric_current", "A"),
                                    _port("v_c", "output", "electric_potential", "V")])
    return resistor, capacitor


def _rc():
    resistor, capacitor = _rc_specs()
    graph = PhysicsGraph("rc", (resistor, capacitor), (
        CouplingEdge("e_v", PortRef("capacitor", "v_c"), PortRef("resistor", "v_c")),
        CouplingEdge("e_i", PortRef("resistor", "i"), PortRef("capacitor", "i")),
    ))

    def resistor_step(_state, inputs, _dt):
        return {"i": ((VS - inputs["v_c"].magnitude_in("V")) / R, "A")}

    def capacitor_step(state, inputs, dt):
        state["v"] = state["v"] + inputs["i"].magnitude_in("A") * dt / C
        return {"v_c": (state["v"], "V")}

    participants = {
        "resistor": _participant(resistor, {}, lambda _s: {"i": ((VS - V0) / R, "A")}, resistor_step),
        "capacitor": _participant(capacitor, {"v": V0}, lambda s: {"v_c": (s["v"], "V")}, capacitor_step),
    }
    return graph, participants


def test_rc_voltage_and_current_are_distinct_ports_and_the_time_state_follows_the_closed_form():
    graph, participants = _rc()
    assert graph.participant("capacitor").port("v_c").dimension != graph.participant("resistor").port("i").dimension
    run = _run(graph, _explicit("rc", ("resistor", "capacitor"), RC_DT, RC_N), participants, "rc")
    assert len(run.windows) == RC_N
    assert all(window.outcome is WindowOutcome.EXPLICIT_COMPLETED for window in run.windows)
    decay = 1.0 - RC_DT / (R * C)
    assert _value(run, "capacitor.v_c") == pytest.approx(VS - (VS - V0) * decay ** RC_N, rel=1e-12)
    assert _value(run, "resistor.i") == pytest.approx((VS - V0) * decay ** (RC_N - 1) / R, rel=1e-12)


def test_rc_a_current_cannot_be_wired_into_a_voltage_input():
    resistor, capacitor = _rc_specs()
    meter = _spec("voltmeter", [_port("v", "input", "electric_potential", "V")])
    with pytest.raises(InvalidScientificProblem, match=r"connects \["):
        PhysicsGraph("rc-miswired", (resistor, capacitor, meter), (
            CouplingEdge("e_bad", PortRef("resistor", "i"), PortRef("voltmeter", "v")),
        ))


def test_gap_no_generic_ode_participant_exists():
    """CDAR-4 / audit A-11: the RC capacitor needs a hand-written callback; there is no generic ODE/DAE participant.
    An attribute probe, not an import of a module that does not exist (the dependency guard reads import strings)."""
    import engcore.execution.multiphysics as runtime_package
    assert not hasattr(runtime_package, "OdeParticipant")


# ==== 2. Mechanical spring-mass =====================================================================================
#
# spring: F = -k x                                     mass (state x, v): m dv/dt = F, dx/dt = v
# Serial explicit order (spring, mass): x lagged, F forward and held over the window; the mass updates
#     v' = v + F dt / m,   x' = x + v' dt          (symplectic Euler, omega^2 = k / m)
# which conserves EXACTLY  Q = v^2 + omega^2 x^2 - omega^2 dt x v.  Derivation: with v' = v - omega^2 dt x and
# x' = x + dt v',  omega^2 x'^2 - omega^2 dt x' v' = omega^2 x' (x' - dt v') = omega^2 x' x, so
# Q' = v'^2 + omega^2 x x' = v'^2 + omega^2 x^2 + omega^2 dt x v' = v' (v' + omega^2 dt x) + omega^2 x^2 = v' v + omega^2 x^2
# and v' v = v^2 - omega^2 dt x v, so Q' = Q.
# Energy H = (v^2 + omega^2 x^2) / 2 = Q / 2 + omega^2 dt x v / 2, and |x v| <= H / omega, so from rest (H_0 = Q / 2):
#     |H_N - H_0| <= (omega dt / 2) H_N <= (omega dt / 2) H_0 / (1 - omega dt / 2).

K, M, X0 = 4.0, 1.0, 0.1                       # N/m, kg, m      (omega = 2 rad/s)
SM_DT, SM_N = 1 / 32, 320                      # 10 s, omega dt = 0.0625
# A force is energy per length, so a force edge falls under the energy-density rule of every scalar edge
# (composition/conversion.py ENERGY_DERIVED_DIMENSIONS; graph.py builds a QuantityDependency per scalar edge) and must
# state a transport.  This is the statement; test_gap_a_force_edge_must_speak_in_energy_terms pins the finding.
FORCE_DECLARATION = "a mechanical contact force, delivered whole; no energy is modelled as crossing this edge"


def _spring_mass_specs():
    spring = _spec("spring", [_port("x", "input", "displacement", "m"), _port("f", "output", "force", "N")])
    mass = _spec("mass", [_port("f", "input", "force", "N"), _port("x", "output", "displacement", "m"),
                          _port("v", "output", "velocity", "m/s")])
    return spring, mass


def _spring_mass():
    spring, mass = _spring_mass_specs()
    graph = PhysicsGraph("spring-mass", (spring, mass), (
        CouplingEdge("e_x", PortRef("mass", "x"), PortRef("spring", "x")),
        CouplingEdge("e_f", PortRef("spring", "f"), PortRef("mass", "f"), transport_declaration=FORCE_DECLARATION),
    ))

    def spring_step(_state, inputs, _dt):
        return {"f": (-K * inputs["x"].magnitude_in("m"), "N")}

    def mass_outputs(state):
        return {"x": (state["x"], "m"), "v": (state["v"], "m/s")}

    def mass_step(state, inputs, dt):
        state["v"] = state["v"] + inputs["f"].magnitude_in("N") * dt / M
        state["x"] = state["x"] + state["v"] * dt
        return mass_outputs(state)

    participants = {
        "spring": _participant(spring, {}, lambda _s: {"f": (-K * X0, "N")}, spring_step),
        "mass": _participant(mass, {"x": X0, "v": 0.0}, mass_outputs, mass_step),
    }
    return graph, participants


def test_spring_mass_force_and_displacement_move_with_the_exact_discrete_invariant():
    graph, participants = _spring_mass()
    run = _run(graph, _explicit("spring-mass", ("spring", "mass"), SM_DT, SM_N), participants, "spring-mass")
    assert len(run.windows) == SM_N
    x, v = _value(run, "mass.x"), _value(run, "mass.v")
    w2 = K / M
    q0 = w2 * X0 ** 2
    assert v ** 2 + w2 * x ** 2 - w2 * SM_DT * x * v == pytest.approx(q0, rel=1e-10)
    h0, hn = 0.5 * q0, 0.5 * (v ** 2 + w2 * x ** 2)
    omega_dt = w2 ** 0.5 * SM_DT
    assert abs(hn - h0) <= (omega_dt / 2) * h0 / (1 - omega_dt / 2) * (1 + 1e-9)
    assert abs(v) > 1e-3                       # it moved: 10 s is ~3.2 periods, not a turning point


def test_gap_a_force_edge_must_speak_in_energy_terms():
    """Design finding, audit gap A-13 (CDAR-1 / CDAR-2): the energy-density rule applies to SCALAR edges too, not only
    to field edges -- graph.py builds a QuantityDependency for every scalar edge -- so an undeclared scalar force edge
    is refused as "a density of energy or power" crossing silently.  This is deliberate -- the rule
    refuses silence, not mechanics, and its message names the force case -- but because a dimension cannot tell a
    force from an energy per length, every mechanical edge must answer it in free prose rather than a declared role."""
    spring, mass = _spring_mass_specs()
    with pytest.raises(InvalidScientificProblem, match="energy or power"):
        PhysicsGraph("spring-mass-undeclared", (spring, mass), (
            CouplingEdge("e_f", PortRef("spring", "f"), PortRef("mass", "f")),
        ))


def test_gap_a_same_dimension_different_meaning_edge_is_accepted():
    """CDAR-1 / audit A-1: edges compare dimensions, not meaning.  Once the energy-density rule is answered, a spring
    STIFFNESS (N/m) feeds a SURFACE-TENSION input (N/m, also J/m^2) unrefused; ``quantity`` is never compared."""
    stiffness = _spec("spring", [_port("k", "output", "spring_stiffness", "N/m")])
    film = _spec("film", [_port("gamma", "input", "surface_tension", "N/m")])
    graph = PhysicsGraph("meaning", (stiffness, film), (
        CouplingEdge("e", PortRef("spring", "k"), PortRef("film", "gamma"), transport_declaration="delivered whole"),
    ))
    assert graph.edge("e").edge_id == "e"


def test_gap_a_frame_transform_is_a_static_rotation_only():
    """CDAR-9 / audit A-9: a frame transform is a fixed matrix between two named frames; it carries no translation,
    no angular velocity and no time dependence, so a moving or rotating frame cannot be declared."""
    import dataclasses

    from engcore.scientific.multiphysics.frames import FrameTransform
    assert [f.name for f in dataclasses.fields(FrameTransform)] == ["transform_id", "source_frame", "target_frame",
                                                                    "matrix"]


# ==== 3. Chemical mixing ============================================================================================
#
# Two well-mixed tanks (volume V each) exchange a flow Q both ways.  Each tank holds an amount n (mol); over a window
#     n' = (n + inflow dt) / (1 + r),   r = Q dt / V,   outflow = Q n' / V
# (backward Euler in its own outflow), and it reports the outflow it actually used.  Implicit serial coupling
# (tank_a, tank_b): the b -> a edge is lagged and converged tightly, so at convergence each tank receives what the
# other reported sending, and the coupled window is the backward-Euler step of the pair:
#     sum:        (n_a' + n_b') (1 + r) = n_a + n_b + r (n_a' + n_b')     =>  n_a' + n_b' = n_a + n_b   (inventory)
#     difference: (n_a' - n_b') (1 + r) = n_a - n_b - r (n_a' - n_b')     =>  d' = d / (1 + 2 r)
# The declared balance binds each exchange's SOURCE (left) to its RECEIVED (right).  On a scalar edge with no conversion
# RECEIVED is the source value in the target's unit (execution/multiphysics/transfer.py), so this balance is satisfied
# by construction and cannot fail here; for the lagged e_ba it is not even the iterate tank_a used.  It proves only that
# a non-energy balance is declarable and recorded.  The INVENTORY assertion is the real conservation check -- and that
# a tank's storage cannot be bound into a balance is itself a CDAR-2 finding (audit A-2).

V, Q, NA0, NB0 = 1.0, 0.2, 1.0, 0.0            # m^3, m^3/s, mol, mol
MIX_DT, MIX_N = 0.5, 20                        # 10 s, r = 0.1


def _mixing(*, leak=False):
    ports = [_port("inflow", "input", "species_flow", "mol/s"), _port("outflow", "output", "species_flow", "mol/s"),
             _port("amount", "output", "species_amount", "mol"),
             _port("concentration", "output", "concentration", "mol/m**3")]
    tank_a, tank_b = _spec("tank_a", ports), _spec("tank_b", ports)
    terms = [ConservationTermBinding(f"{edge}_{measure.value}", edge, side, measure)
             for edge in ("e_ab", "e_ba")
             for side, measure in ((BalanceSide.LEFT, TransferMeasure.SOURCE),
                                   (BalanceSide.RIGHT, TransferMeasure.RECEIVED))]
    if leak:   # the CDAR-2 probe: a declared species loss on the exchange
        terms.append(ConservationTermBinding("leak", "e_ab", BalanceSide.RIGHT, TransferMeasure.LOSS, loss_form="leak"))
    balance = CoupledConservation("species", tuple(terms), Quantity(1e-12, "mol/s"),
                                  "each exchange arrives whole in the other tank")
    graph = PhysicsGraph("mixing", (tank_a, tank_b), (
        CouplingEdge("e_ab", PortRef("tank_a", "outflow"), PortRef("tank_b", "inflow")),
        CouplingEdge("e_ba", PortRef("tank_b", "outflow"), PortRef("tank_a", "inflow")),
    ), conservation=(balance,))

    def outputs(state):
        n = state["n"]
        return {"outflow": (Q * n / V, "mol/s"), "amount": (n, "mol"), "concentration": (n / V, "mol/m**3")}

    def step(state, inputs, dt):
        state["n"] = (state["n"] + inputs["inflow"].magnitude_in("mol/s") * dt) / (1.0 + Q * dt / V)
        return outputs(state)

    participants = {"tank_a": _participant(tank_a, {"n": NA0}, outputs, step),
                    "tank_b": _participant(tank_b, {"n": NB0}, outputs, step)}
    plan = CouplingPlan("mixing", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(MIX_DT * MIX_N, "s"), Quantity(MIX_DT, "s")),
                        ("tank_a", "tank_b"), (ConvergenceCriterion("e_ba", 1e-13, Quantity(1e-15, "mol/s")),),
                        RelaxationPolicy(), 200, True)
    return graph, plan, participants


def test_mixing_conserves_the_species_inventory_and_its_declared_balance_holds():
    graph, plan, participants = _mixing()
    run = _run(graph, plan, participants, "mixing")
    assert len(run.windows) == MIX_N
    assert all(window.outcome is WindowOutcome.CONVERGED for window in run.windows)
    n_a, n_b = _value(run, "tank_a.amount"), _value(run, "tank_b.amount")
    assert n_a + n_b == pytest.approx(NA0 + NB0, rel=1e-9)
    r = Q * MIX_DT / V
    assert n_a - n_b == pytest.approx((NA0 - NB0) / (1.0 + 2.0 * r) ** MIX_N, rel=1e-6)
    assert run.final_outputs["_conservation_status"]["required"] == "pass"   # by construction; see the comment above
    require_conservation(run)


def test_gap_a_species_loss_cannot_be_declared_on_a_mass_flow_edge():
    """CDAR-2 / audit A-2: a loss term needs an EnergyConversion on its edge; a species leak cannot be expressed."""
    with pytest.raises(InvalidScientificProblem, match="with no conversion"):
        _mixing(leak=True)
