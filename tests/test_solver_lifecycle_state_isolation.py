"""Problem-specific execution state must never leak between independent solves.

SL-2 / SL-3 of the solver lifecycle hardening sprint: reproductions written
against the lifecycle as it exists at ``f8cfd9a``, before any fix.

Every solver adapter keeps a binding table on the instance, keyed by
``problem_id``: ``_bound`` (battery, lumped thermal, resistance property),
``_circuits`` (electrical DC), and the same shape elsewhere. ``prepare`` reads
the table and copies what it finds into the ``PreparedSolve``. A
``SolverRegistry`` stores one instance per solver and hands the same object to
every caller of ``resolve``.

Each test below asserts the invariant the sprint must establish, so a failure
here is a reproduced leak, not a broken test:

    Two independent prepared solves may execute in any order, or concurrently,
    without reading or mutating each other's problem-specific state.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from engcore.domains.battery import cell as bat
from engcore.domains.battery import solver as bsol
from engcore.domains.electrical import material as mat
from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    build_dc_problem,
)
from engcore.domains.thermal_models import lumped as lump
from engcore.scientific.solvers.registry import SolverRegistry
from engcore.scientific.units.quantity import Quantity

K = "kelvin"
GND = ElectricalNode("gnd", is_reference=True)

#: Reproduced at ``f8cfd9a``, before any fix. Strict, so a reproduction that stops
#: failing is reported rather than passing quietly; the fix removes these marks.
REPRODUCED = pytest.mark.xfail(
    strict=True,
    reason="SL-2 reproduction: problem-specific state leaks between independent solves at f8cfd9a",
)


# ---- builders ---------------------------------------------------------------
class cases:  # noqa: N801 - mirrors tests/domains/battery/battery_cases, importable from tests/
    @staticmethod
    def build_cell() -> bat.CellSpecification:
        return bat.CellSpecification(
            cell_id="CELL-1",
            nominal_capacity=Quantity(2.5, "ampere_hour"),
            internal_resistance=Quantity(0.030, "ohm"),
            open_circuit_voltage_at_full=Quantity(4.2, "volt"),
            open_circuit_voltage_at_empty=Quantity(3.0, "volt"),
            coulombic_efficiency=Quantity(0.99, "dimensionless"),
        )

    @staticmethod
    def build_load(current: Quantity = Quantity(2.5, "ampere")) -> bat.DischargeLoad:
        return bat.DischargeLoad(
            load_id="LOAD-1",
            current=current,
            initial_state_of_charge=Quantity(0.90, "dimensionless"),
            cell_temperature=Quantity(298.15, K),
            duration=Quantity(120.0, "second"),
        )


def _body() -> lump.ThermalBody:
    return lump.ThermalBody(
        body_id="B1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
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


# ---- one request, run to completion on the solver it is given ----------------
def _lumped(solver, watts: float) -> dict[str, float]:
    body = _body()
    problem = lump.build_lumped_thermal_problem(body)
    solver.bind_body(body, problem.problem_id, heat_input=Quantity(watts, "watt"))
    return dict(solver.solve(solver.prepare(problem)).values)


def _resistance(solver, kelvin: float) -> dict[str, float]:
    conductor = _conductor()
    problem = mat.build_resistance_problem(conductor)
    solver.bind_conductor(conductor, problem.problem_id, temperature=Quantity(kelvin, K))
    return dict(solver.solve(solver.prepare(problem)).values)


def _battery(solver, amps: float) -> dict[str, float]:
    cell = cases.build_cell()
    load = cases.build_load(current=Quantity(amps, "ampere"))
    problem = bat.build_battery_problem(cell, load)
    solver.bind_cell(cell, load, problem.problem_id)
    return dict(solver.solve(solver.prepare(problem)).values)


def _dc(solver, r1: float) -> dict[str, float]:
    circuit = _circuit(r1)
    problem = build_dc_problem(circuit)
    solver.bind_circuit(circuit, problem.problem_id)
    return dict(solver.solve(solver.prepare(problem)).values)


CASES = {
    "lumped": (lump.LumpedThermalSolver, _lumped, 1.0, 4.0),
    "resistance": (mat.ResistancePropertySolver, _resistance, 340.0, 400.0),
    "battery": (bsol.BatteryCellSolver, _battery, 2.5, 1.0),
    "dc": (ElectricalDCSolver, _dc, 1.0, 5.0),
}


def _isolated(name: str, point: float) -> dict[str, float]:
    factory, run, _a, _b = CASES[name]
    return run(factory(), point)


# ---- A. sequential contamination ----------------------------------------------
@pytest.mark.parametrize(
    "name", [pytest.param(n, marks=REPRODUCED) if n == "dc" else n for n in sorted(CASES)]
)
def test_a_sequential_a_then_b_then_a_leaves_a_unchanged(name):
    factory, run, a, b = CASES[name]
    shared = factory()
    first = run(shared, a)
    other = run(shared, b)
    again = run(shared, a)
    assert first == _isolated(name, a)
    assert other == _isolated(name, b)
    assert again == first


# ---- B. interleaved lifecycle ---------------------------------------------------
@REPRODUCED
def test_b_lumped_a_bound_b_bound_a_prepared_solves_a():
    shared = lump.LumpedThermalSolver()
    body = _body()
    problem = lump.build_lumped_thermal_problem(body)
    shared.bind_body(body, problem.problem_id, heat_input=Quantity(1.0, "watt"))  # request A
    shared.bind_body(body, problem.problem_id, heat_input=Quantity(4.0, "watt"))  # request B
    result_a = dict(shared.solve(shared.prepare(problem)).values)                 # request A resumes
    assert result_a == _isolated("lumped", 1.0)


@REPRODUCED
def test_b_resistance_a_bound_b_bound_a_prepared_solves_a():
    shared = mat.ResistancePropertySolver()
    conductor = _conductor()
    problem = mat.build_resistance_problem(conductor)
    shared.bind_conductor(conductor, problem.problem_id, temperature=Quantity(340.0, K))
    shared.bind_conductor(conductor, problem.problem_id, temperature=Quantity(400.0, K))
    result_a = dict(shared.solve(shared.prepare(problem)).values)
    assert result_a == _isolated("resistance", 340.0)


@REPRODUCED
def test_b_battery_a_bound_b_bound_a_prepared_solves_a():
    shared = bsol.BatteryCellSolver()
    cell = cases.build_cell()
    load_a = cases.build_load(current=Quantity(2.5, "ampere"))
    load_b = cases.build_load(current=Quantity(1.0, "ampere"))
    problem_a = bat.build_battery_problem(cell, load_a)
    assert bat.build_battery_problem(cell, load_b).problem_id == problem_a.problem_id
    shared.bind_cell(cell, load_a, problem_a.problem_id)
    shared.bind_cell(cell, load_b, problem_a.problem_id)
    result_a = dict(shared.solve(shared.prepare(problem_a)).values)
    assert result_a == _isolated("battery", 2.5)


def test_b_dc_a_prepared_then_b_bound_then_a_solved_is_unaffected():
    shared = ElectricalDCSolver()
    circuit_a = _circuit(1.0)
    problem_a = build_dc_problem(circuit_a)
    shared.bind_circuit(circuit_a, problem_a.problem_id)
    prepared_a = shared.prepare(problem_a)
    try:
        shared.bind_circuit(_circuit(5.0), build_dc_problem(_circuit(5.0)).problem_id)
    except Exception:
        pass
    assert dict(shared.solve(prepared_a).values) == _isolated("dc", 1.0)


@REPRODUCED
def test_b_dc_a_stale_binding_does_not_refuse_an_independent_request():
    """Request B describes a different circuit with the same circuit id."""
    shared = ElectricalDCSolver()
    assert _dc(shared, 1.0) == _isolated("dc", 1.0)
    assert _dc(shared, 5.0) == _isolated("dc", 5.0)


# ---- C. concurrency ---------------------------------------------------------------
@pytest.mark.parametrize(
    "name", [pytest.param(n, marks=REPRODUCED) if n == "dc" else n for n in sorted(CASES)]
)
def test_c_concurrent_mixed_requests_on_one_shared_solver_match_isolated_baselines(name):
    factory, run, a, b = CASES[name]
    baselines = {a: _isolated(name, a), b: _isolated(name, b)}
    shared = factory()
    points = [a if index % 2 else b for index in range(48)]
    gate = threading.Barrier(8)

    def request(point):
        try:
            gate.wait(timeout=5)
        except threading.BrokenBarrierError:
            pass
        try:
            return point, run(shared, point), None
        except Exception as exc:  # a refusal caused by another request is a leak too
            return point, None, exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(request, points))
    wrong = [(p, got, err) for p, got, err in outcomes if err is not None or got != baselines[p]]
    assert not wrong, f"{len(wrong)}/{len(outcomes)} requests saw another request's state: {wrong[:3]}"


BIND_THEN_PREPARE = {
    "lumped": (
        lump.LumpedThermalSolver,
        lambda: lump.build_lumped_thermal_problem(_body()),
        lambda solver, problem, point: solver.bind_body(
            _body(), problem.problem_id, heat_input=Quantity(point, "watt")
        ),
    ),
    "resistance": (
        mat.ResistancePropertySolver,
        lambda: mat.build_resistance_problem(_conductor()),
        lambda solver, problem, point: solver.bind_conductor(
            _conductor(), problem.problem_id, temperature=Quantity(point, K)
        ),
    ),
    "battery": (
        bsol.BatteryCellSolver,
        lambda: bat.build_battery_problem(cases.build_cell(), cases.build_load()),
        lambda solver, problem, point: solver.bind_cell(
            cases.build_cell(), cases.build_load(current=Quantity(point, "ampere")),
            problem.problem_id,
        ),
    ),
}


@REPRODUCED
@pytest.mark.parametrize("name", sorted(BIND_THEN_PREPARE))
def test_c_concurrent_requests_through_the_bind_prepare_window_stay_isolated(name):
    """Real threads, with the window between bind and prepare forced open.

    Every request binds its own operating point, then all requests wait at one
    barrier, then each prepares and solves. With one shared solver the table
    holds only the last bind by the time anyone prepares.
    """
    factory, make_problem, bind = BIND_THEN_PREPARE[name]
    _factory, _run, a, b = CASES[name]
    baselines = {a: _isolated(name, a), b: _isolated(name, b)}
    shared = factory()
    points = [a if index % 2 else b for index in range(8)]
    between = threading.Barrier(len(points))

    def request(point):
        problem = make_problem()
        bind(shared, problem, point)
        between.wait(timeout=10)
        return point, dict(shared.solve(shared.prepare(problem)).values)

    with ThreadPoolExecutor(max_workers=len(points)) as pool:
        outcomes = list(pool.map(request, points))
    wrong = [(point, got) for point, got in outcomes if got != baselines[point]]
    assert not wrong, f"{len(wrong)}/{len(outcomes)} requests solved another request's operating point"


# ---- D. failure cleanup --------------------------------------------------------------
@REPRODUCED
def test_d_lumped_a_failed_request_does_not_poison_the_next_valid_one():
    shared = lump.LumpedThermalSolver()
    wrong_body = lump.ThermalBody(
        body_id="B1",
        heat_capacity=Quantity(9.0, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(120.0, "second"),
    )
    problem = lump.build_lumped_thermal_problem(_body())
    shared.bind_body(wrong_body, problem.problem_id, heat_input=Quantity(1.0, "watt"))
    with pytest.raises(Exception):
        shared.prepare(problem)  # the first request fails: its problem describes another body
    assert _lumped(shared, 1.0) == _isolated("lumped", 1.0)


@REPRODUCED
def test_d_dc_a_failed_request_does_not_poison_the_next_valid_one():
    shared = ElectricalDCSolver()
    problem_a = build_dc_problem(_circuit(1.0))
    shared.bind_circuit(_circuit(5.0), problem_a.problem_id)
    with pytest.raises(Exception):
        shared.prepare(problem_a)
    assert _dc(shared, 1.0) == _isolated("dc", 1.0)


# ---- E. repeated execution -------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(CASES))
def test_e_the_same_request_repeated_is_deterministic(name):
    factory, run, a, _b = CASES[name]
    shared = factory()
    results = [run(shared, a) for _ in range(5)]
    assert all(result == results[0] for result in results)
    assert results[0] == _isolated(name, a)


# ---- the other bound-state solvers: what does prepare capture? ---------------------------
# These stop at ``prepare`` and read what it captured, so no stiff integration, no
# refinement sweep and no external process runs. Each rebinding below is one the
# domain allows on purpose (same physics, another tolerance, resolution or
# realization) or, for the external provider, one it accepts without checking.

@REPRODUCED
def test_b_cstr_a_bound_b_rebinds_a_tolerance_a_prepares_at_its_own_tolerance():
    from engcore.domains.kinetics.cstr.problem import build_cstr_problem
    from engcore.domains.kinetics.cstr.solver import CSTRSolver
    from experiments.kinetics_k15.k15_config import HOLDOUT

    run_a = HOLDOUT.build()  # HOLDOUT is the regime spec; build() is the ReactorRun
    run_b = run_a.with_integration(
        run_a.integration.with_tolerances(
            rtol=run_a.integration.rtol * 100.0,
            atol_concentration=run_a.integration.atol_concentration * 100.0,
            atol_temperature=run_a.integration.atol_temperature * 100.0,
        )
    )
    problem = build_cstr_problem(run_a)
    shared = CSTRSolver()
    shared.bind_run(run_a, problem.problem_id)
    shared.bind_run(run_b, problem.problem_id)
    prepared = shared.prepare(problem)
    isolated = CSTRSolver()
    isolated.bind_run(run_a, problem.problem_id)
    assert prepared.settings.tolerances == isolated.prepare(problem).settings.tolerances


def _slab(n_cells: int = 16, n_steps: int = 20):
    from engcore.domains.thermal.conduction1d.problem import ConductionSlab, SlabDiscretization

    return ConductionSlab(
        slab_id="S1",
        length=Quantity(1.0, "meter"),
        diffusivity=Quantity(1e-4, "meter**2/second"),
        end_time=Quantity(10.0, "second"),
        discretization=SlabDiscretization(n_cells, n_steps),
    )


@REPRODUCED
def test_b_conduction_a_bound_b_rebinds_a_resolution_a_prepares_at_its_own():
    from engcore.domains.thermal.conduction1d.problem import (
        SlabDiscretization,
        build_conduction_problem,
    )
    from engcore.domains.thermal.conduction1d.solver import Conduction1DSolver

    slab_a = _slab(16, 20)
    slab_b = slab_a.with_discretization(SlabDiscretization(64, 80))
    problem = build_conduction_problem(slab_a)
    shared = Conduction1DSolver()
    shared.bind_slab(slab_a, problem.problem_id)
    shared.bind_slab(slab_b, problem.problem_id)
    assert shared.prepare(problem).payload.slab.discretization == slab_a.discretization


@REPRODUCED
def test_b_scheme_a_bound_b_rebinds_a_realization_a_prepares_its_own():
    from engcore.domains.thermal.conduction1d.problem import build_conduction_problem
    from engcore.domains.thermal_models.conduction1d_schemes import (
        EXPLICIT_REALIZATION,
        IMPLICIT_REALIZATION,
        sparse_scheme_solver,
    )

    slab = _slab()
    problem = build_conduction_problem(slab)
    shared = sparse_scheme_solver()
    shared.bind(problem.problem_id, slab, IMPLICIT_REALIZATION)
    shared.bind(problem.problem_id, slab, EXPLICIT_REALIZATION)
    assert shared.prepare(problem).payload.realization.key == IMPLICIT_REALIZATION.key


@REPRODUCED
def test_b_ngspice_a_bound_b_rebinds_a_circuit_a_is_not_refused_or_swapped():
    from engcore.domains.electrical import ngspice as ng

    class _NoProcess(ng.NgspiceInvocation):
        def probe_version(self) -> str:  # prepare records the identity; nothing is launched
            return "stub-0"

    shared = ng.NgspiceDCSolver(invocation=_NoProcess())
    circuit_a, circuit_b = _circuit(1.0), _circuit(5.0)
    problem_a = build_dc_problem(circuit_a)
    shared.bind_circuit(circuit_a, problem_a.problem_id)
    shared.bind_circuit(circuit_b, build_dc_problem(circuit_b).problem_id)  # same default id
    prepared = shared.prepare(problem_a)
    assert prepared.payload.circuit.fingerprint() == circuit_a.fingerprint()


# ---- registry -------------------------------------------------------------------------
@REPRODUCED
def test_registry_resolution_exposes_no_shared_problem_state_between_requests():
    registry = SolverRegistry([lump.LumpedThermalSolver()])
    body = _body()
    problem = lump.build_lumped_thermal_problem(body)
    for_a = registry.resolve(problem)
    for_b = registry.resolve(problem)
    for_a.bind_body(body, problem.problem_id, heat_input=Quantity(1.0, "watt"))
    for_b.bind_body(body, problem.problem_id, heat_input=Quantity(4.0, "watt"))
    assert dict(for_a.solve(for_a.prepare(problem)).values) == _isolated("lumped", 1.0)
