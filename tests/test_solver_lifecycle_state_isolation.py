"""Problem-specific execution state must never leak between independent solves.

The solver lifecycle hardening sprint. ``test(solver): reproduce lifecycle state
leakage`` recorded the defects at ``f8cfd9a`` as strict xfails against one shared
solver instance; this module states the same scenarios against the lifecycle
the core now exposes, and adds the concurrency and failure-isolation matrix.

Every solver adapter binds its system -- and the operating point, numerics or
realization beside it -- into a table on the instance, keyed by problem id, and
``prepare`` reads that table. A solver instance is therefore a *session*: the
requests made through it. ``SolverRegistry`` used to store one instance per
solver and return it from every ``resolve``, so every caller shared one session;
two requests then solved at each other's operating point, and a failed request's
binding refused the next. The registry now stores a factory, never a session,
and hands every request a new session.

The invariants under test:

    Two independent prepared solves may execute in any order, or concurrently,
    without reading or mutating each other's problem-specific state.

    Registry resolution does not expose shared mutable execution state.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from engcore.domains.battery import cell as bat
from engcore.domains.battery import solver as bsol
from engcore.domains.electrical import material as mat
from engcore.domains.electrical import ngspice as ng
from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    build_dc_problem,
)
from engcore.domains.electrical.dc.errors import CircuitBindingError
from engcore.domains.kinetics.cstr.problem import build_cstr_problem
from engcore.domains.kinetics.cstr.solver import CSTRSolver
from engcore.domains.thermal.conduction1d.problem import (
    ConductionSlab,
    SlabDiscretization,
    build_conduction_problem,
)
from engcore.domains.thermal.conduction1d.solver import Conduction1DSolver
from engcore.domains.thermal_models import lumped as lump
from engcore.domains.thermal_models.conduction1d_schemes import (
    EXPLICIT_REALIZATION,
    IMPLICIT_REALIZATION,
    sparse_scheme_solver,
)
from engcore.scientific.errors import AmbiguousSolverError, InvalidScientificProblem
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.solvers.registry import SolverDefinition, SolverRegistry
from engcore.scientific.units.quantity import Quantity
from experiments.kinetics_k15.k15_config import HOLDOUT

K = "kelvin"
GND = ElectricalNode("gnd", is_reference=True)


# ---- builders ---------------------------------------------------------------
def _body(capacity: float = 2.5) -> lump.ThermalBody:
    return lump.ThermalBody(
        body_id="B1",
        heat_capacity=Quantity(capacity, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(120.0, "second"),
    )


def _conductor() -> mat.TemperatureDependentConductor:
    return mat.TemperatureDependentConductor(
        component_id="R1",
        reference_resistance=Quantity(10.0, "ohm"),
        temperature_coefficient=Quantity(0.00393, "1/kelvin"),
        reference_temperature=Quantity(293.15, K),
    )


def _cell() -> bat.CellSpecification:
    return bat.CellSpecification(
        cell_id="CELL-1",
        nominal_capacity=Quantity(2.5, "ampere_hour"),
        internal_resistance=Quantity(0.030, "ohm"),
        open_circuit_voltage_at_full=Quantity(4.2, "volt"),
        open_circuit_voltage_at_empty=Quantity(3.0, "volt"),
        coulombic_efficiency=Quantity(0.99, "dimensionless"),
    )


def _load(amps: float = 2.5) -> bat.DischargeLoad:
    return bat.DischargeLoad(
        load_id="LOAD-1",
        current=Quantity(amps, "ampere"),
        initial_state_of_charge=Quantity(0.90, "dimensionless"),
        cell_temperature=Quantity(298.15, K),
        duration=Quantity(120.0, "second"),
    )


def _circuit(r1: float) -> DCCircuit:
    return DCCircuit(
        circuit_id="divider",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(r1, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),),
    )


def _slab(n_cells: int = 16, n_steps: int = 20) -> ConductionSlab:
    return ConductionSlab(
        slab_id="S1",
        length=Quantity(1.0, "meter"),
        diffusivity=Quantity(1e-4, "meter**2/second"),
        end_time=Quantity(10.0, "second"),
        discretization=SlabDiscretization(n_cells, n_steps),
    )


_RUN = HOLDOUT.build()  # HOLDOUT is the regime spec; build() is the ReactorRun


def _run_at(scale: float):
    return _RUN.with_integration(
        _RUN.integration.with_tolerances(
            rtol=_RUN.integration.rtol * scale,
            atol_concentration=_RUN.integration.atol_concentration * scale,
            atol_temperature=_RUN.integration.atol_temperature * scale,
        )
    )


class _NoProcess(ng.NgspiceInvocation):
    def probe_version(self) -> str:  # prepare records the identity; nothing is launched
        return "stub-0"


def _ngspice() -> ng.NgspiceDCSolver:
    return ng.NgspiceDCSolver(invocation=_NoProcess())


# ---- one kind of request per solver -------------------------------------------
# (factory, make_problem, bind(session, problem, point), observe(session, problem), (a, b))
# ``make_problem`` takes the operating point: DC and ngspice carry it in the circuit.
# CSTR, conduction, scheme and ngspice stop at ``prepare`` and read what it
# captured, so no stiff integration, refinement sweep or external process runs.
def _solved(session, problem):
    return dict(session.solve(session.prepare(problem)).values)


CASES = {
    "lumped": (
        lump.LumpedThermalSolver,
        lambda point: lump.build_lumped_thermal_problem(_body()),
        lambda s, p, point: s.bind_body(_body(), p.problem_id, heat_input=Quantity(point, "watt")),
        _solved,
        (1.0, 4.0),
    ),
    "resistance": (
        mat.ResistancePropertySolver,
        lambda point: mat.build_resistance_problem(_conductor()),
        lambda s, p, point: s.bind_conductor(_conductor(), p.problem_id, temperature=Quantity(point, K)),
        _solved,
        (340.0, 400.0),
    ),
    "battery": (
        bsol.BatteryCellSolver,
        lambda point: bat.build_battery_problem(_cell(), _load(point)),
        lambda s, p, point: s.bind_cell(_cell(), _load(point), p.problem_id),
        _solved,
        (2.5, 1.0),
    ),
    "dc": (
        ElectricalDCSolver,
        lambda point: build_dc_problem(_circuit(point)),
        lambda s, p, point: s.bind_circuit(_circuit(point), p.problem_id),
        _solved,
        (1.0, 5.0),
    ),
    "ngspice": (
        _ngspice,
        lambda point: build_dc_problem(_circuit(point)),
        lambda s, p, point: s.bind_circuit(_circuit(point), p.problem_id),
        lambda s, p: s.prepare(p).payload.circuit.fingerprint(),
        (1.0, 5.0),
    ),
    "cstr": (
        CSTRSolver,
        lambda point: build_cstr_problem(_RUN),
        lambda s, p, point: s.bind_run(_run_at(point), p.problem_id),
        lambda s, p: dict(s.prepare(p).settings.tolerances),
        (1.0, 100.0),
    ),
    "conduction": (
        Conduction1DSolver,
        lambda point: build_conduction_problem(_slab()),
        lambda s, p, point: s.bind_slab(_slab(int(point), int(point) + 4), p.problem_id),
        lambda s, p: s.prepare(p).payload.slab.discretization,
        (16.0, 64.0),
    ),
    "scheme": (
        sparse_scheme_solver,
        lambda point: build_conduction_problem(_slab()),
        lambda s, p, point: s.bind(
            p.problem_id, _slab(), IMPLICIT_REALIZATION if point == 0.0 else EXPLICIT_REALIZATION
        ),
        lambda s, p: s.prepare(p).payload.realization.key,
        (0.0, 1.0),
    ),
}
NAMES = sorted(CASES)
SOLVING = ("battery", "dc", "lumped", "resistance")


def _registry(*names: str) -> SolverRegistry:
    return SolverRegistry([CASES[name][0] for name in names])


def _request(registry: SolverRegistry, name: str, point: float):
    """One independent request, from resolution to what it observed."""
    _factory, make_problem, bind, observe, _points = CASES[name]
    problem = make_problem(point)
    session = registry.resolve(problem)
    bind(session, problem, point)
    return observe(session, problem)


def _isolated(name: str, point: float):
    """The baseline: a registry, and a request, of its own."""
    return _request(_registry(name), name, point)


def test_the_two_operating_points_of_every_case_are_distinguishable():
    for name in NAMES:
        a, b = CASES[name][4]
        assert _isolated(name, a) != _isolated(name, b), name


# ---- 1. sequential ------------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_1_a_then_b_then_a_through_one_registry(name):
    registry = _registry(name)
    a, b = CASES[name][4]
    first = _request(registry, name, a)
    other = _request(registry, name, b)
    again = _request(registry, name, a)
    assert first == _isolated(name, a)
    assert other == _isolated(name, b)
    assert again == first


# ---- 2. interleaved lifecycle: the reproduced window ------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_2_a_bound_b_bound_a_prepared_captures_a(name):
    """Two requests resolve, both bind the same default problem id, then A prepares."""
    _factory, make_problem, bind, observe, (a, b) = CASES[name]
    registry = _registry(name)
    problem_a, problem_b = make_problem(a), make_problem(b)
    assert problem_a.problem_id == problem_b.problem_id  # the default ids ignore the operating point
    session_a = registry.resolve(problem_a)
    session_b = registry.resolve(problem_b)
    bind(session_a, problem_a, a)
    bind(session_b, problem_b, b)
    assert observe(session_a, problem_a) == _isolated(name, a)
    assert observe(session_b, problem_b) == _isolated(name, b)


@pytest.mark.parametrize("name", SOLVING)
def test_2_a_prepared_b_prepared_b_solved_a_solved(name):
    _factory, make_problem, bind, _observe, (a, b) = CASES[name]
    registry = _registry(name)
    problem_a, problem_b = make_problem(a), make_problem(b)
    session_a, session_b = registry.resolve(problem_a), registry.resolve(problem_b)
    bind(session_a, problem_a, a)
    prepared_a = session_a.prepare(problem_a)
    bind(session_b, problem_b, b)
    prepared_b = session_b.prepare(problem_b)
    assert dict(session_b.solve(prepared_b).values) == _isolated(name, b)
    assert dict(session_a.solve(prepared_a).values) == _isolated(name, a)


# ---- 3. concurrent A and B, the bind -> prepare window forced open -----------------------
@pytest.mark.parametrize("name", NAMES)
def test_3_concurrent_requests_through_the_bind_prepare_window_stay_isolated(name):
    """Real threads and one registry. Every request resolves and binds, all of them
    wait at one barrier, then each prepares. Against one shared solver this left
    only the last bind in the table by the time anyone prepared."""
    _factory, make_problem, bind, observe, (a, b) = CASES[name]
    registry = _registry(name)
    baselines = {a: _isolated(name, a), b: _isolated(name, b)}
    points = [a if index % 2 else b for index in range(8)]
    between = threading.Barrier(len(points))

    def request(point):
        problem = make_problem(point)
        session = registry.resolve(problem)
        bind(session, problem, point)
        between.wait(timeout=10)
        return point, observe(session, problem)

    with ThreadPoolExecutor(max_workers=len(points)) as pool:
        outcomes = list(pool.map(request, points))
    wrong = [(point, got) for point, got in outcomes if got != baselines[point]]
    assert not wrong, f"{len(wrong)}/{len(outcomes)} requests saw another request's state"


# ---- 4. many mixed concurrent solves -------------------------------------------------------
@pytest.mark.parametrize("count", [20, 100])
def test_4_many_mixed_concurrent_solves_through_one_registry(count):
    registry = _registry(*SOLVING)
    baselines = {(n, p): _isolated(n, p) for n in SOLVING for p in CASES[n][4]}
    work = [
        (name, CASES[name][4][(index // len(SOLVING)) % 2])
        for index, name in zip(range(count), itertools.cycle(SOLVING))
    ]

    def request(item):
        name, point = item
        try:
            return item, _request(registry, name, point), None
        except Exception as exc:  # a refusal caused by another request is a leak too
            return item, None, exc

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(request, work))
    wrong = [(item, err) for item, got, err in outcomes if err is not None or got != baselines[item]]
    assert not wrong, f"{len(wrong)}/{len(outcomes)} requests cross-contaminated: {wrong[:4]}"


# ---- 5, 6. failure isolation ----------------------------------------------------------------
def test_5_a_failed_lumped_request_does_not_affect_the_next_valid_one():
    registry = _registry("lumped")
    problem = lump.build_lumped_thermal_problem(_body())
    failed = registry.resolve(problem)
    failed.bind_body(_body(capacity=9.0), problem.problem_id, heat_input=Quantity(1.0, "watt"))
    with pytest.raises(InvalidScientificProblem):
        failed.prepare(problem)  # its problem describes another body
    assert _request(registry, "lumped", 1.0) == _isolated("lumped", 1.0)


def test_5_a_failed_dc_request_does_not_affect_the_next_valid_one():
    registry = _registry("dc")
    problem_a = build_dc_problem(_circuit(1.0))
    failed = registry.resolve(problem_a)
    failed.bind_circuit(_circuit(5.0), problem_a.problem_id)
    with pytest.raises(CircuitBindingError):
        failed.prepare(problem_a)  # the problem describes another circuit
    assert _request(registry, "dc", 1.0) == _isolated("dc", 1.0)
    assert _request(registry, "dc", 5.0) == _isolated("dc", 5.0)


STAGES = ("bind", "prepare", "solve", "backend", "result")


def _failing_once(base, stage: str):
    """A factory whose first *request* session raises at ``stage``.

    Call 0 is the registry's probe, so call 1 is the first session handed out.
    ``backend`` fails inside ``solve`` after the payload is read; ``result``
    fails turning raw output into metrics. Nothing is reset after a failure:
    the failed session is dropped with its request.
    """
    calls = itertools.count()

    class _Failing(base):
        fail_at = None

        def _fail(self, here):
            if self.fail_at == here:
                raise RuntimeError(f"injected {here} failure")

        def bind_body(self, *args, **kwargs):
            self._fail("bind")
            return super().bind_body(*args, **kwargs)

        def bind_circuit(self, *args, **kwargs):
            self._fail("bind")
            return super().bind_circuit(*args, **kwargs)

        def prepare(self, problem):
            self._fail("prepare")
            return super().prepare(problem)

        def solve(self, prepared):
            self._fail("solve")
            raw = super().solve(prepared)
            self._fail("backend")
            return raw

        def extract_metrics(self, prepared, raw):
            self._fail("result")
            return super().extract_metrics(prepared, raw)

    def factory():
        session = _Failing()
        if next(calls) == 1:
            session.fail_at = stage
        return session

    return factory


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("name", ["dc", "lumped"])
def test_6_an_exception_at_any_stage_does_not_reach_the_next_request(name, stage):
    _factory, make_problem, bind, _observe, (a, b) = CASES[name]
    registry = SolverRegistry([_failing_once(CASES[name][0], stage)])
    problem = make_problem(b)
    failed = registry.resolve(problem)
    with pytest.raises(RuntimeError, match=f"injected {stage} failure"):
        bind(failed, problem, b)
        prepared = failed.prepare(problem)
        failed.extract_metrics(prepared, failed.solve(prepared))
    # the next request: a different operating point under the same problem id
    problem = make_problem(a)
    session = registry.resolve(problem)
    bind(session, problem, a)
    prepared = session.prepare(problem)
    raw = session.solve(prepared)
    assert dict(raw.values) == _isolated(name, a)
    assert session.extract_metrics(prepared, raw)


# ---- 7. the same definition reused ------------------------------------------------------------
def test_7_one_definition_reused_hands_every_request_its_own_session():
    registry = _registry("lumped")
    problem = lump.build_lumped_thermal_problem(_body())
    sessions = [registry.resolve(problem) for _ in range(20)]
    assert len({id(s) for s in sessions}) == 20
    assert all(type(s) is lump.LumpedThermalSolver for s in sessions)
    for watts, session in enumerate(sessions):
        session.bind_body(_body(), problem.problem_id, heat_input=Quantity(float(watts), "watt"))
    assert [_solved(s, problem) for s in sessions] == [
        _isolated("lumped", float(watts)) for watts in range(20)
    ]


# ---- 8. different implementations --------------------------------------------------------------
def test_8_different_implementations_in_one_registry_stay_separate():
    registry = SolverRegistry([ElectricalDCSolver, _ngspice, lump.LumpedThermalSolver, bsol.BatteryCellSolver])
    problem = build_dc_problem(_circuit(1.0))
    with pytest.raises(AmbiguousSolverError):
        registry.resolve(problem)
    native, external = registry.candidates(problem)
    native.bind_circuit(_circuit(1.0), problem.problem_id)
    external.bind_circuit(_circuit(5.0), problem.problem_id)
    assert _solved(native, problem) == _isolated("dc", 1.0)
    assert native.bound_circuit(problem.problem_id).fingerprint() == _circuit(1.0).fingerprint()
    assert _request(registry, "lumped", 4.0) == _isolated("lumped", 4.0)
    assert _request(registry, "battery", 1.0) == _isolated("battery", 1.0)


# ---- 9. a registry singleton under concurrency --------------------------------------------------
REGISTRY_SINGLETON = _registry(*SOLVING)


def test_9_a_module_level_registry_under_concurrency_never_shares_or_binds_its_probe():
    problem = lump.build_lumped_thermal_problem(_body())
    definition = REGISTRY_SINGLETON.definition(*lump.LumpedThermalSolver().identity.key)
    with ThreadPoolExecutor(max_workers=16) as pool:
        sessions = list(pool.map(lambda _: REGISTRY_SINGLETON.resolve(problem), range(64)))
    assert len({id(s) for s in sessions}) == 64
    assert all(s is not definition._probe for s in sessions)
    for session in sessions:
        session.bind_body(_body(), problem.problem_id, heat_input=Quantity(4.0, "watt"))
    assert definition._probe._bound == {}
    assert _request(REGISTRY_SINGLETON, "lumped", 1.0) == _isolated("lumped", 1.0)


# ---- 10. prepared solves own their state ----------------------------------------------------------
@pytest.mark.parametrize("name", SOLVING)
def test_10_a_prepared_solve_carries_its_state_through_copies_and_other_sessions(name):
    """``solve`` reads the prepared solve and nothing bound on the session: a copy of
    it, or another session of the same solver, computes the same request."""
    _factory, make_problem, bind, _observe, (a, b) = CASES[name]
    registry = _registry(name)
    problem = make_problem(a)
    session = registry.resolve(problem)
    bind(session, problem, a)
    prepared = session.prepare(problem)
    stranger = registry.resolve(make_problem(b))
    bind(stranger, make_problem(b), b)
    expected = _isolated(name, a)
    assert dict(session.solve(copy.copy(prepared)).values) == expected
    assert dict(session.solve(dataclasses.replace(prepared)).values) == expected
    assert dict(stranger.solve(prepared).values) == expected
    with pytest.raises(dataclasses.FrozenInstanceError):
        prepared.payload = None  # type: ignore[misc]


# ---- 10b. one prepared solve, executed more than once ----------------------------------------------
# Reproduced at ``6e69699`` as strict xfails: ``CSTRSolver.prepare`` assembled the
# right-hand side over the evaluation-budget counter, and every ``solve`` of that
# prepared solve charged the same counter. Execution now assembles its own.
EXECUTED =("battery", "conduction", "cstr", "dc", "lumped", "resistance", "scheme")


def _executable(name):
    if name == "cstr":
        return (
            CSTRSolver,
            lambda point: build_cstr_problem(_RUN),
            lambda s, p, point: s.bind_run(_RUN, p.problem_id),
            None,
            (1.0, 1.0),
        )
    return CASES[name]


def _prepared_once(name):
    factory, make_problem, bind, _observe, (a, _b) = _executable(name)
    session = factory()
    problem = make_problem(a)
    bind(session, problem, a)
    return session, session.prepare(problem)


def _raw_record(raw) -> str:
    record = raw.to_dict()
    record.pop("wall_seconds")
    return repr(record)  # repr, so a NaN diagnostic compares equal to itself


@pytest.mark.parametrize("name", EXECUTED)
def test_10b_one_prepared_solve_executed_twice_or_concurrently_is_the_same_as_once(name):
    fresh_session, fresh = _prepared_once(name)
    once = _raw_record(fresh_session.solve(fresh))
    session, prepared = _prepared_once(name)
    assert _raw_record(session.solve(prepared)) == once
    assert _raw_record(session.solve(prepared)) == once
    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent = list(pool.map(lambda _: _raw_record(session.solve(prepared)), range(4)))
    assert concurrent == [once] * 4


def test_10c_a_cstr_prepared_solve_spends_a_fresh_budget_on_each_execution():
    """A budget a little above what one execution needs: the second execution of the
    same prepared solve must not start from what the first one spent."""
    session, prepared = _prepared_once("cstr")
    need = int(session.solve(prepared).diagnostics["rhs_evaluations_completed"])
    tight = _RUN.with_integration(dataclasses.replace(_RUN.integration, max_rhs_evaluations=need + 5))
    solver = CSTRSolver()
    problem = build_cstr_problem(tight)
    solver.bind_run(tight, problem.problem_id)
    prepared = solver.prepare(problem)
    first, second = solver.solve(prepared), solver.solve(prepared)
    assert first.convergence is ConvergenceState.CONVERGED
    assert second.convergence is ConvergenceState.CONVERGED
    assert second.diagnostics["rhs_evaluations_completed"] == need


# ---- registry contract (SL-7) ------------------------------------------------------------------------
@pytest.mark.parametrize("instance", [lump.LumpedThermalSolver(), ElectricalDCSolver(), _ngspice()])
def test_registering_a_constructed_solver_instance_is_refused(instance):
    with pytest.raises(TypeError, match="factories, not solver instances"):
        SolverRegistry([instance])
    with pytest.raises(TypeError, match="factories, not solver instances"):
        SolverRegistry().register(instance)


def test_every_way_out_of_the_registry_is_a_new_session():
    registry = SolverRegistry([ElectricalDCSolver])
    problem = build_dc_problem(_circuit(1.0))
    key = ElectricalDCSolver().identity.key
    handed = [
        registry.resolve(problem),
        registry.resolve(problem),
        registry.get(*key),
        *registry.candidates(problem),
        *registry.list(),
        *registry,
    ]
    assert len({id(s) for s in handed}) == len(handed)
    definition = registry.definition(*key)
    assert isinstance(definition, SolverDefinition)
    assert all(s is not definition._probe for s in handed)
    assert definition.identity == handed[0].identity


def test_a_factory_that_returns_one_shared_instance_is_refused():
    shared = lump.LumpedThermalSolver()
    registry = SolverRegistry([lambda: shared])  # the probe is that instance
    with pytest.raises(TypeError, match="already produced"):
        registry.resolve(lump.build_lumped_thermal_problem(_body()))


def test_a_factory_that_reissues_a_session_is_refused():
    made = [lump.LumpedThermalSolver(), lump.LumpedThermalSolver()]
    calls = itertools.count()
    registry = SolverRegistry([lambda: made[min(next(calls), 1)]])
    problem = lump.build_lumped_thermal_problem(_body())
    registry.resolve(problem)
    with pytest.raises(TypeError, match="already produced"):
        registry.resolve(problem)


class _Alternative(ElectricalDCSolver):
    @property
    def identity(self):
        return SolverIdentity("electrical.dc.alternative", "0.1.0")


def test_a_factory_whose_sessions_are_another_solver_is_refused():
    calls = itertools.count()
    registry = SolverRegistry([lambda: ElectricalDCSolver() if next(calls) == 0 else _Alternative()])
    with pytest.raises(TypeError, match="identifying as electrical.dc.alternative"):
        registry.resolve(build_dc_problem(_circuit(1.0)))


def test_a_selection_rule_chooses_among_new_sessions_and_cannot_substitute_one():
    registry = SolverRegistry([ElectricalDCSolver, _Alternative])
    problem = build_dc_problem(_circuit(1.0))
    seen = []

    def rule(candidates):
        seen.append(candidates)
        return candidates[0]

    first = registry.resolve(problem, selection_rule=rule)
    second = registry.resolve(problem, selection_rule=rule)
    assert first is not second
    assert not {id(s) for s in seen[0]} & {id(s) for s in seen[1]}
    with pytest.raises(AmbiguousSolverError, match="does not support"):
        registry.resolve(problem, selection_rule=lambda candidates: ElectricalDCSolver())


# ---- repeated execution -------------------------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_repeated_identical_requests_are_deterministic(name):
    registry = _registry(name)
    point = CASES[name][4][0]
    results = [_request(registry, name, point) for _ in range(5)]
    assert all(result == results[0] for result in results)


# ---- the contract boundary -------------------------------------------------------------------------------
def test_a_directly_constructed_solver_is_one_session():
    """What the registry no longer does, a caller can still do by hand: one solver
    instance is one set of bindings. The DC adapter refuses to let one problem id
    describe two circuits within a session; the independent request gets its own
    session and is served (``test_1``/``test_2``)."""
    session = ElectricalDCSolver()
    problem = build_dc_problem(_circuit(1.0))
    session.bind_circuit(_circuit(1.0), problem.problem_id)
    with pytest.raises(CircuitBindingError):
        session.bind_circuit(_circuit(5.0), problem.problem_id)
