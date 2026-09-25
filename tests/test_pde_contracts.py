"""BIG 8 provider-neutral PDE contracts (no provider imported).

The real FEniCSx solves live in providers/fenicsx/tests.

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

GMSH_OK, GMSH_DETAIL = gmsh_available()

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
