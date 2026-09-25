"""BIG 8 PDE/FEM: real FEniCSx/PETSc execution through the provider-neutral contracts.

Run from the repository root with the provider on the path, e.g.
``PYTHONPATH=src:providers/fenicsx <fenicsx-python> -m pytest providers/fenicsx/tests``.

Real solves run only where dolfinx + PETSc import (the conda-forge `fenicsx`
environment in this session); elsewhere the provider tests are SKIPPED with the
provider's own reason, and the contract tests still run.  Nothing here is
validation: FEM convergence, mesh refinement and agreement with an analytic
1D solution are numerical corroboration only.  Material data are the
illustrative BIG 5 fixtures (plus illustrative elastic constants below).
"""

from __future__ import annotations

import hashlib
import importlib.util

import numpy as np
import pytest

from engcore.materials import ApplicabilityRange, MaterialState
from engcore.numerical.core import ProviderUnavailable
from engcore.pde import (
    PLANE_STRESS_ELASTICITY, STEADY_DIFFUSION, TRANSIENT_DIFFUSION, BCKind, BoundaryCondition, CoefficientBinding,
    DiscretizationSpec, FacetRole, PDEProblem, PDERefusal, PhysicalModel, SourcedQuantity, TransientSpec,
)
from forge_fenicsx import FenicsxProvider, fenicsx_available
from engcore.scenarios import NamedQuantity, TimePoint, TimeWindow
from engcore.scientific.solvers.protocol import ConvergenceState, SolverSettings
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import (
    CoordinateFrame, Location, PhysicalGroup, Rank, RegionMaterialMap, SpatialFieldDefinition, SpatialMesh,
    gmsh_available, gmsh_two_region_plate,
)
from engcore.scientific.fields import CellType

_spec = importlib.util.spec_from_file_location("materials_fixtures", "tests/test_materials_engine.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

FENICS_OK, FENICS_DETAIL = fenicsx_available()
GMSH_OK, GMSH_DETAIL = gmsh_available()
needs_fenics = pytest.mark.skipif(not (FENICS_OK and GMSH_OK), reason=f"FEniCSx: {FENICS_DETAIL}; Gmsh: {GMSH_DETAIL}")

HEAT = PhysicalModel("heat.fourier_conduction", "1", "steady Fourier conduction, isotropic k, no source", ("small temperature variation within each material datum's range",))
SOLVER = SolverSettings({"rtol": 1e-12, "residual_rtol": 1e-9}, {"ksp_type": "preonly", "pc_type": "lu", "max_iterations": 1})
L1, L2, H = 0.1, 0.1, 0.1


def prescribed(q, why):
    return SourcedQuantity(q, "prescribed", {"declared_by": "test", "why": why})


def plate(size=0.02):
    return gmsh_two_region_plate(length=L1 + L2, height=H, split=L1, size=size)


def conductivity(mesh, moisture=0.05):
    props, _ = M._alloy_set()
    board = M._board_set()
    alloy = MaterialState(M.ALLOY, (NamedQuantity("temperature", Quantity(450, "K")),), "solid")
    wool = MaterialState(M.BOARD, (NamedQuantity("moisture_content", Quantity(moisture, "dimensionless")),
                                   NamedQuantity("temperature", Quantity(293.15, "K"))))
    binding = RegionMaterialMap(mesh, ((mesh.region("left_plate"), alloy), (mesh.region("right_plate"), wool)))
    field, resolved = binding.property_field({M.ALLOY.digest: props, M.BOARD.digest: board}, "thermal_conductivity", "W/(m*K)", "k")
    return field, resolved


ROLES = {"left": FacetRole.EXTERNAL_BOUNDARY, "right": FacetRole.EXTERNAL_BOUNDARY, "bottom": FacetRole.EXTERNAL_BOUNDARY, "top": FacetRole.EXTERNAL_BOUNDARY}


def steady_problem(mesh, *, left=Quantity(400, "K"), right=Quantity(300, "K"), moisture=0.05, bcs=None, roles=None, unknown_unit="K"):
    k, _ = conductivity(mesh, moisture)
    insulated = prescribed(Quantity(0, "W/m^2"), "declared adiabatic")
    bcs = bcs or (
        BoundaryCondition(BCKind.DIRICHLET, "left", prescribed(left, "hot face")),
        BoundaryCondition(BCKind.DIRICHLET, "right", prescribed(right, "cold face")),
        BoundaryCondition(BCKind.NEUMANN, "top", insulated),
        BoundaryCondition(BCKind.NEUMANN, "bottom", insulated),
    )
    return PDEProblem("plate-steady", mesh, HEAT, STEADY_DIFFUSION,
                      SpatialFieldDefinition("T", "temperature", unknown_unit, Location.NODE, Rank.SCALAR),
                      (CoefficientBinding("conductivity", field=k),), bcs, roles or ROLES, DiscretizationSpec(), SOLVER)


def analytic_series(x, k1, k2, t_hot=400.0, t_cold=300.0):
    q = (t_hot - t_cold) / (L1 / k1 + L2 / k2)
    ti = t_hot - q * L1 / k1
    return np.where(x <= L1, t_hot - q * x / k1, ti - q * (x - L1) / k2)


# ---- A. steady heat -----------------------------------------------------------


@needs_fenics
def test_steady_two_material_conduction_matches_series_solution_and_is_a_big7_field():
    mesh = plate()
    problem = steady_problem(mesh)
    rec = FenicsxProvider().execute(problem)
    assert rec.succeeded and rec.convergence is ConvergenceState.CONVERGED
    assert rec.diagnostics.relative_true_residuals[0] <= 1e-9
    T = rec.field
    assert T.mesh.digest == mesh.digest and T.definition.unit == "kelvin" and T.derivation.value == "computed"
    assert rec.execution_identity in T.provenance and problem.digest in T.provenance
    exact = analytic_series(mesh.coordinates[:, 0], 215.0, 0.045)
    assert np.max(np.abs(T.values - exact)) < 1e-6  # P1 reproduces the piecewise-linear 1D solution (corroboration only)
    assert rec.to_dict()["classification"] == "pde_execution_not_scientific_evidence"


@needs_fenics
def test_material_change_changes_solution_and_identity():
    mesh = plate()
    dry = FenicsxProvider().execute(steady_problem(mesh, moisture=0.0))
    wet = FenicsxProvider().execute(steady_problem(mesh, moisture=0.10))
    assert dry.problem_digest != wet.problem_digest
    xi = np.isclose(mesh.coordinates[:, 0], L1)
    assert not np.allclose(dry.field.values[xi], wet.field.values[xi])


@needs_fenics
def test_celsius_boundary_value_is_converted_not_confused():
    mesh = plate()
    k_ref = FenicsxProvider().execute(steady_problem(mesh))
    c = FenicsxProvider().execute(steady_problem(mesh, left=Quantity(126.85, "degC"), right=Quantity(26.85, "degC")))
    assert np.allclose(k_ref.field.values, c.field.values, atol=1e-9)
    assert k_ref.problem_digest != c.problem_digest  # declared differently, recorded differently


def test_identity_changes_with_bc_and_mesh_and_refusals():
    mesh = gmsh_two_region_plate(length=0.2, height=0.1, split=0.1, size=0.02) if GMSH_OK else pytest.skip(GMSH_DETAIL)
    base = steady_problem(mesh)
    assert steady_problem(mesh, left=Quantity(401, "K")).digest != base.digest
    assert steady_problem(plate(0.025)).digest != base.digest
    with pytest.raises(PDERefusal, match="the unknown is kelvin"):
        steady_problem(mesh, left=Quantity(400, "W/m^2"))
    with pytest.raises(PDERefusal, match="ratio-scale"):
        steady_problem(mesh, unknown_unit="degC")
    with pytest.raises(PDERefusal, match="no declared condition"):
        steady_problem(mesh, bcs=(BoundaryCondition(BCKind.DIRICHLET, "left", prescribed(Quantity(400, "K"), "hot")),))
    with pytest.raises(PDERefusal, match="without a declared facet role"):
        steady_problem(mesh, roles={"left": FacetRole.EXTERNAL_BOUNDARY})
    with pytest.raises(PDERefusal, match="singular"):
        insulated = prescribed(Quantity(0, "W/m^2"), "adiabatic")
        steady_problem(mesh, bcs=tuple(BoundaryCondition(BCKind.NEUMANN, g, insulated) for g in ("left", "right", "top", "bottom")))
    with pytest.raises(PDERefusal, match="anonymous"):
        SourcedQuantity(Quantity(1, "K"), "prescribed", {})


def test_missing_or_unknown_material_property_refuses_before_solve():
    mesh = gmsh_two_region_plate(length=0.2, height=0.1, split=0.1, size=0.02) if GMSH_OK else pytest.skip(GMSH_DETAIL)
    with pytest.raises(Exception, match="UNKNOWN"):
        conductivity(mesh, moisture=0.5)  # beyond tabulated moisture: resolution refuses
    with pytest.raises(PDERefusal, match="never defaulted"):
        PDEProblem("p", mesh, HEAT, STEADY_DIFFUSION, SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR),
                   (), steady_problem(mesh).boundary_conditions, ROLES, DiscretizationSpec(), SOLVER)


def interface_mesh():
    """Two-region fixture with an explicit INTERNAL interface facet group at x = L1."""
    nx, ny = 4, 2
    xs, ys = np.linspace(0, L1 + L2, nx + 1), np.linspace(0, H, ny + 1)
    coords = np.array([[x, y] for y in ys for x in xs])
    nid = lambda i, j: j * (nx + 1) + i  # noqa: E731
    cells, tags = [], []
    for j in range(ny):
        for i in range(nx):
            a, b, c, d = nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)
            cells += [[a, b, c], [a, c, d]]
            tags += [1 if i < nx // 2 else 2] * 2
    facets = [[nid(0, j), nid(0, j + 1)] for j in range(ny)] + [[nid(nx, j), nid(nx, j + 1)] for j in range(ny)] \
        + [[nid(i, 0), nid(i + 1, 0)] for i in range(nx)] + [[nid(i, ny), nid(i + 1, ny)] for i in range(nx)] \
        + [[nid(nx // 2, j), nid(nx // 2, j + 1)] for j in range(ny)]
    ftags = [11] * ny + [12] * ny + [13] * nx + [14] * nx + [15] * ny
    groups = (PhysicalGroup("left_plate", "cells", 1), PhysicalGroup("right_plate", "cells", 2), PhysicalGroup("left", "facets", 11),
              PhysicalGroup("right", "facets", 12), PhysicalGroup("bottom", "facets", 13), PhysicalGroup("top", "facets", 14),
              PhysicalGroup("interface", "facets", 15))
    return SpatialMesh(coordinates=coords, cells=cells, cell_type=CellType.TRIANGLE, frame=CoordinateFrame("plate-xy", 2),
                       cell_tags=tags, facets=facets, facet_tags=ftags, groups=groups)


def test_interface_roles_are_checked_against_topology():
    mesh = interface_mesh()
    roles = dict(ROLES, interface=FacetRole.INTERNAL_INTERFACE)
    ok = steady_problem(mesh, roles=roles)
    assert ok.identity()["facet_roles"]["interface"] == "internal_interface"
    with pytest.raises(PDERefusal, match="declared external"):
        steady_problem(mesh, roles=dict(ROLES, interface=FacetRole.EXTERNAL_BOUNDARY))
    with pytest.raises(PDERefusal, match="declared an interface"):
        steady_problem(mesh, roles=dict(ROLES, left=FacetRole.INTERNAL_INTERFACE))
    bcs = steady_problem(mesh, roles=roles).boundary_conditions + (BoundaryCondition(BCKind.DIRICHLET, "interface", prescribed(Quantity(350, "K"), "x")),)
    with pytest.raises(PDERefusal, match="apply to external boundaries"):
        steady_problem(mesh, roles=roles, bcs=bcs)


def test_provider_unavailable_is_explicit(monkeypatch):
    import forge_fenicsx as fx
    monkeypatch.setattr(fx, "fenicsx_available", lambda: (False, "ModuleNotFoundError: simulated"))
    with pytest.raises(ProviderUnavailable, match="simulated"):
        fx.FenicsxProvider().execute(steady_problem(interface_mesh(), roles=dict(ROLES, interface=FacetRole.INTERNAL_INTERFACE)))


# ---- B. vector: plane-stress elasticity ---------------------------------------


def elastic_property_sets():
    rows_a = [("E-a", "youngs_modulus", Quantity(70e9, "Pa"), None, (ApplicabilityRange("temperature", Quantity(250, "K"), Quantity(350, "K")),), "solid", "compiled", None),
              ("nu-a", "poisson_ratio", Quantity(0.33, "dimensionless"), None, (ApplicabilityRange("temperature", Quantity(250, "K"), Quantity(350, "K")),), "solid", "compiled", None)]
    rows_b = [("E-b", "youngs_modulus", Quantity(2e6, "Pa"), None, (ApplicabilityRange("temperature", Quantity(250, "K"), Quantity(350, "K")),), "", "compiled", None),
              ("nu-b", "poisson_ratio", Quantity(0.2, "dimensionless"), None, (ApplicabilityRange("temperature", Quantity(250, "K"), Quantity(350, "K")),), "", "compiled", None)]
    a, _ = M._dataset(M.ALLOY, rows_a, source_id="fixture-alloy-elastic", locator="tests::elastic-a", set_id="alloy-elastic")
    b, _ = M._dataset(M.BOARD, rows_b, source_id="fixture-board-elastic", locator="tests::elastic-b", set_id="board-elastic")
    return {M.ALLOY.digest: a, M.BOARD.digest: b}


@needs_fenics
def test_plane_stress_elasticity_returns_framed_vector_field():
    mesh = plate()
    sets = elastic_property_sets()
    room = NamedQuantity("temperature", Quantity(293.15, "K"))
    binding = RegionMaterialMap(mesh, ((mesh.region("left_plate"), MaterialState(M.ALLOY, (room,), "solid")),
                                       (mesh.region("right_plate"), MaterialState(M.BOARD, (room,)))))
    E, _ = binding.property_field(sets, "youngs_modulus", "Pa", "E")
    nu, _ = binding.property_field(sets, "poisson_ratio", "dimensionless", "nu")
    free = SourcedQuantity(Quantity(0, "Pa"), "prescribed", {"declared": "traction-free"})
    pull = SourcedQuantity(Quantity(1e4, "Pa"), "prescribed", {"declared": "uniform tension"})
    problem = PDEProblem(
        "plate-elastic", mesh, PhysicalModel("solid.linear_elastic_plane_stress", "1", "small-strain isotropic plane stress"),
        PLANE_STRESS_ELASTICITY, SpatialFieldDefinition("u", "displacement", "m", Location.NODE, Rank.VECTOR, frame_id="plate-xy"),
        (CoefficientBinding("youngs_modulus", field=E), CoefficientBinding("poisson_ratio", field=nu),
         CoefficientBinding("thickness", constant=SourcedQuantity(Quantity(5, "mm"), "prescribed", {"declared": "plate thickness"}))),
        (BoundaryCondition(BCKind.DIRICHLET, "left", SourcedQuantity(Quantity(0, "m"), "prescribed", {"declared": "clamped"})),
         BoundaryCondition(BCKind.NEUMANN, "right", pull, vector_value=(Quantity(1e4, "Pa"), Quantity(0, "Pa"))),
         BoundaryCondition(BCKind.NEUMANN, "top", free, vector_value=(Quantity(0, "Pa"), Quantity(0, "Pa"))),
         BoundaryCondition(BCKind.NEUMANN, "bottom", free, vector_value=(Quantity(0, "Pa"), Quantity(0, "Pa")))),
        ROLES, DiscretizationSpec(degree=2), SOLVER)
    rec = FenicsxProvider().execute(problem)
    assert rec.succeeded
    u = rec.field
    assert u.definition.rank is Rank.VECTOR and u.definition.frame_id == "plate-xy" and u.values.shape == (mesh.node_count, 2)
    right = np.isclose(mesh.coordinates[:, 0], L1 + L2)
    ux_right = u.values[right, 0].mean()
    # soft right half dominates: ux ~ sigma*L2/E_b (uniaxial estimate, corroboration only)
    assert 0.3 * 1e4 * L2 / 2e6 < ux_right < 3 * 1e4 * L2 / 2e6
    with pytest.raises(PDERefusal, match="natural datum"):
        BoundaryCondition(BCKind.NEUMANN, "right", pull, vector_value=(Quantity(1, "N"), Quantity(0, "N")))
        PDEProblem("bad", mesh, problem.model, PLANE_STRESS_ELASTICITY, problem.unknown, problem.coefficients,
                   problem.boundary_conditions[:1] + (BoundaryCondition(BCKind.NEUMANN, "right", pull, vector_value=(Quantity(1, "N"), Quantity(0, "N"))),) + problem.boundary_conditions[2:],
                   ROLES, DiscretizationSpec(), SOLVER)


# ---- C + D. transient heat driven by BIG 3 environment on a BIG 2 window -----


def ambient_environment(values=(290.0, 270.0), uq=True):
    from engcore.scenarios import (ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource,
                                   EnvironmentTimeline, HistoryEntry, QuantityHistory, ReferenceContext, ScenarioSegment,
                                   ScenarioSpecification, TimeBasis, Timeline)
    basis = TimeBasis("lab", "elapsed", "t0")
    p = lambda s: TimePoint("lab", Quantity(s, "s"))  # noqa: E731
    scenario = ScenarioSpecification("cooling", "1", Quantity(0, "s"), Quantity(100, "s"), segments=(ScenarioSegment("s", Quantity(0, "s"), Quantity(100, "s")),))
    entries = tuple(HistoryEntry(TimeWindow(p(50 * i), p(50 * (i + 1))), NamedQuantity("air", Quantity(v, "K"))) for i, v in enumerate(values) if v is not None)
    hist = QuantityHistory("air-h", "exposure", "air", "K", entries)
    tl = Timeline.from_scenario(scenario, timeline_id="cooling", basis=basis, histories=(hist,))
    ch = EnvironmentChannel("air", "ambient_temperature", "K", "met", ReferenceContext("lab-air", "lab", "enu"), TimeWindow(p(0), p(100)),
                            ChannelRepresentation.INTERVAL_HISTORY, history_id="air-h")
    return EnvironmentTimeline("lab-env", tl, EnvironmentKindRegistry.standard(),
                               (EnvironmentSource("met", "measured", "lab", hashlib.sha256(b"met").hexdigest(), "1"),), (ch,)), p


def environment_schedule(env, p, starts=(0, 50)):
    out = []
    for s in starts:
        v = env.channel_value("air", p(s))
        if v.status.value != "known":
            raise PDERefusal(f"ambient temperature is UNKNOWN at {s} s: {v.reason}")
        out.append((float(s), SourcedQuantity(v.value.value, "environment", v.to_dict())))
    return tuple(out)


def transient_problem(mesh, env, p):
    k, _ = conductivity(mesh)
    c = CoefficientBinding("volumetric_heat_capacity", constant=prescribed(Quantity(2.4e6, "J/(m^3*K)"), "illustrative rho*c"))
    sched = environment_schedule(env, p)
    insulated = prescribed(Quantity(0, "W/m^2"), "adiabatic")
    h = prescribed(Quantity(25, "W/(m^2*K)"), "illustrative film coefficient")
    window = TimeWindow(p(0), p(100))
    return PDEProblem(
        "plate-transient", mesh, HEAT, TRANSIENT_DIFFUSION, SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR),
        (CoefficientBinding("conductivity", field=k), c),
        (BoundaryCondition(BCKind.ROBIN, "left", sched[0][1], coefficient=h),
         BoundaryCondition(BCKind.NEUMANN, "right", insulated), BoundaryCondition(BCKind.NEUMANN, "top", insulated),
         BoundaryCondition(BCKind.NEUMANN, "bottom", insulated)),
        ROLES, DiscretizationSpec(), SOLVER,
        TransientSpec(window, Quantity(10, "s"), prescribed(Quantity(330, "K"), "uniform initial state"),
                      (Quantity(50, "s"), Quantity(100, "s")), breakpoints=(Quantity(50, "s"),)),
        boundary_schedule={"left": sched},
    )


@needs_fenics
def test_transient_heat_with_environment_robin_bc_on_big2_window():
    mesh = plate()
    env, p = ambient_environment()
    problem = transient_problem(mesh, env, p)
    rec = FenicsxProvider().execute(problem)
    assert rec.succeeded and [t for t, _ in rec.fields] == [50.0, 100.0] and rec.diagnostics.steps == 10
    t50, t100 = rec.fields[0][1].values, rec.fields[1][1].values
    assert t100.mean() < t50.mean() < 330.0  # cools toward the colder ambient
    # P1 + backward Euler with a consistent mass matrix has NO discrete maximum
    # principle at this conductivity contrast: a small overshoot above the initial
    # 330 K appears. It is a known numerical artifact, recorded, not hidden.
    overshoot = max(0.0, float(t50.max()) - 330.0)
    assert overshoot < 0.5
    assert any(item["origin"] == "environment" for item in problem.identity()["boundary_schedule"]["left"] for item in [item[1]])
    colder, _ = ambient_environment(values=(290.0, 250.0))
    assert transient_problem(mesh, colder, p).digest != problem.digest


def test_transient_refusals():
    env, p = ambient_environment(values=(290.0, None))
    with pytest.raises(PDERefusal, match="UNKNOWN"):
        environment_schedule(env, p)
    window = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(100, "s")))
    with pytest.raises(PDERefusal, match="integer number of steps"):
        TransientSpec(window, Quantity(15, "s"), prescribed(Quantity(300, "K"), "x"), (Quantity(90, "s"),), breakpoints=(Quantity(50, "s"),))
    with pytest.raises(PDERefusal, match="step grid"):
        TransientSpec(window, Quantity(10, "s"), prescribed(Quantity(300, "K"), "x"), (Quantity(55, "s"),))
    with pytest.raises(PDERefusal, match="outside the authorized window"):
        TransientSpec(window, Quantity(10, "s"), prescribed(Quantity(300, "K"), "x"), (Quantity(200, "s"),))


# ---- E. lifecycle feed-forward into a real PDE --------------------------------


@needs_fenics
def test_lifecycle_moisture_changes_the_next_real_pde_solve():
    from engcore.data import BulkDataResolver, InMemoryBulkStore
    from engcore.domains.hygrothermal.moisture_uptake import LinearWetnessMoistureUptake
    from engcore.execution.multiphysics import (AdvanceResult, CallbackParticipant, InitialStateDefinition, InitialStateReceipt,
                                                InitialStateValue, InitializationResult, MultiphysicsRuntime)
    from engcore.scenarios import InputBinding, StepStatus, run_lifecycle
    from engcore.scientific.multiphysics import (CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
                                                 PortDefinition, PortDirection, PortKind, TimePolicy)
    from engcore.scientific.multiphysics.receipts import StateVariableValue
    from engcore.scientific.results.uncertainty import Uncertainty

    mesh = plate()
    provider = FenicsxProvider()
    solves = []

    def execute(run_id, window, initial_state):
        spec = ParticipantSpec("wall", "model", "1", "realization", "1", "fenicsx", provider.identity.version, "adapter", "1",
                               (PortDefinition("t_interface", PortDirection.OUTPUT, PortKind.SCALAR, "t_interface", "K"),), transient=True)
        held = {}
        unknown = Uncertainty.unknown("FEM output uncertainty not quantified")

        def solve():
            rec = provider.execute(steady_problem(mesh, moisture=held["m"].value.magnitude))
            solves.append(rec)
            xi = np.isclose(mesh.coordinates[:, 0], L1)
            return Quantity(float(rec.field.values[xi].mean()), "K")

        def digest():
            return hashlib.sha256(repr(held["m"].value.magnitude).encode()).hexdigest()

        def initialize_state(instant, state, _i, _u):
            held["m"] = state["moisture_content"]
            receipt = InitialStateReceipt("wall", instant, (state["moisture_content"],), digest())
            return InitializationResult({"t_interface": solve()}, {"t_interface": unknown}, initial_state_receipt=receipt)

        participant = CallbackParticipant(
            spec, initialize=lambda *a: (_ for _ in ()).throw(PDERefusal("explicit state required")),
            advance=lambda req: AdvanceResult(req.end, {"t_interface": solve()}, {"t_interface": unknown}, 1, True),
            initial_state_definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
            initialize_state=initialize_state, state_identity=lambda _t: digest(),
            public_state=lambda _t: (StateVariableValue("moisture_content", held["m"].value, held["m"].uncertainty),))
        start, end = window.start.quantity, window.end.quantity
        plan = CouplingPlan(f"{run_id}-p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(start, end, Quantity(end.magnitude - start.magnitude, "s")))
        store = InMemoryBulkStore()
        runtime = MultiphysicsRuntime(PhysicsGraph(f"{run_id}-g", (spec,), ()), plan, {"wall": participant}, resolver=BulkDataResolver(store), store=store)
        return runtime.run(run_id, external_inputs={}, initial_state=initial_state, scenario_digest=M.SCENARIO.digest)

    p = lambda d: TimePoint("site", Quantity(d, "day"))  # noqa: E731
    chain, runs = run_lifecycle(
        model=LinearWetnessMoistureUptake(k_uptake=Quantity(1e-6, "1/s"), max_wet_time=Quantity(1, "day")),
        environment=M._wet_environment(), participant_id="wall",
        definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
        initial_state={"wall": {"moisture_content": InitialStateValue("moisture_content", Quantity(0.0, "dimensionless"), Uncertainty.unknown("as built"))}},
        windows=tuple(TimeWindow(p(i), p(i + 1)) for i in range(2)), execute=execute, bindings=(InputBinding("wet_time", "wetness"),),
    )
    assert [s.status for s in chain.steps] == [StepStatus.APPLIED] * 2
    t_i = [r.final_outputs["wall.t_interface"]["magnitude"] for r in runs]
    assert t_i[0] != pytest.approx(t_i[1], abs=1e-9)  # wetter board -> higher k -> different interface temperature
    assert len({s.problem_digest for s in solves}) >= 2 and all(s.succeeded for s in solves)


# ---- F. two mesh resolutions (numerical comparison only) ----------------------


@needs_fenics
def test_two_resolutions_are_compared_not_validated():
    coarse = FenicsxProvider().execute(steady_problem(plate(0.025)))
    fine = FenicsxProvider().execute(steady_problem(plate(0.0125)))
    def interface_temp(rec):
        m = rec.field.mesh
        return float(rec.field.values[np.isclose(m.coordinates[:, 0], L1)].mean())
    diff = abs(interface_temp(coarse) - interface_temp(fine))
    comparison = {"classification": "discretization_comparison_not_validation", "coarse": interface_temp(coarse),
                  "fine": interface_temp(fine), "abs_difference_K": diff, "asymptotic_claim": None}
    assert comparison["asymptotic_claim"] is None and diff < 1e-6  # piecewise-linear exact solution: both resolutions reproduce it
    assert coarse.execution_identity != fine.execution_identity


@needs_fenics
def test_replay_reproduces_identity_and_values_within_declared_tolerance():
    mesh = plate()
    a = FenicsxProvider().execute(steady_problem(mesh))
    b = FenicsxProvider().execute(steady_problem(mesh))
    assert a.execution_identity == b.execution_identity and np.allclose(a.field.values, b.field.values, rtol=0, atol=1e-10)


@needs_fenics
def test_failed_solve_exposes_no_field():
    mesh = plate()
    starving = SolverSettings({"rtol": 1e-14, "residual_rtol": 1e-12}, {"ksp_type": "cg", "pc_type": "none", "max_iterations": 1})
    base = steady_problem(mesh)
    problem = PDEProblem(base.problem_id, mesh, base.model, base.operator, base.unknown, base.coefficients, base.boundary_conditions,
                         base.facet_roles, base.discretization, starving)
    rec = FenicsxProvider().execute(problem)
    assert not rec.succeeded and rec.fields == () and "KSP reason" in rec.reason
    with pytest.raises(PDERefusal, match="execution failed"):
        rec.field
