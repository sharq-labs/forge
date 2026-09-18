"""Batch 16 of the 2026-09-16 core re-audit: boundary completeness per EDGE (I-24, R-56).

`require_complete_boundary` promises that "every edge of the support carries exactly one condition" and
refuses "two conditions on one region" as a contradiction with a silent winner. **It does not check edges.**
Both of its checks are keyed by REGION ID, and the region list comes from the caller -- so a second
`MeshRegion` on an edge that already has one lets two contradictory conditions share that edge, and a subset
of regions is accepted as a complete boundary.

The audited end-to-end case: a 9x9 plate whose left edge carries a 400 K Dirichlet condition AND a
0 W/m^2 Neumann condition through two region ids solves, reports `field_finite`,
`field_linear_system_residual` and `boundary_conditions_held` all PASS, and returns a field whose maximum is
300.00000000019827 K -- where the correct solve gives 400 K. `SteadyConductionProblem.edges` is a dict
comprehension keyed by edge, so the last condition wins; the assembly and `_worst_dirichlet_error` both read
it, so the dropped Dirichlet condition is never imposed and never checked, and the provenance records only
the winning flux law.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH16_THRESHOLD_PROTOCOL.json`.

Six of these were audited reproductions, recorded as `xfail(strict=True)` in commit **e0749c17** and
confirmed there to fail against the pre-batch tree (6 failed, 2 passed under `--runxfail`): four on DID NOT
RAISE, which is an assertion about a refusal that is absent, and two on their own assertions. The markers
came off with the implementation. The two unmarked tests are no-regression guards on the shape every in-tree
caller uses and on the number the audited run should have produced.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.domains.thermal_models.conduction2d import (
    SteadyConductionProblem,
    plate_problem,
    solve_steady_conduction,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    BoundaryEdge,
    FieldBoundaryCondition,
    FieldDefinition,
    MeshRegion,
    StructuredMesh,
    boundary_regions,
    require_complete_boundary,
)
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.scientific.units.quantity import Quantity

CONDUCTIVITY = Quantity(2.5, "watt/meter/kelvin")
KELVIN = "kelvin"
FLUX = "watt/meter**2"


def _mesh(nodes: int = 9, mesh_id: str = "plate") -> StructuredMesh:
    return StructuredMesh(
        mesh_id=mesh_id,
        length_x=Quantity(1.0, "meter"),
        length_y=Quantity(1.0, "meter"),
        nodes_x=nodes,
        nodes_y=nodes,
    )


def _field(mesh: StructuredMesh) -> FieldDefinition:
    return FieldDefinition(field_id="T", unit=KELVIN, mesh_id=mesh.mesh_id)


def _dirichlet(region_id: str, kelvin: float = 300.0, name: str | None = None):
    return FieldBoundaryCondition(
        name=name or f"fixed-{region_id}", field_id="T", region_id=region_id,
        kind=BoundaryKind.DIRICHLET, value=Quantity(kelvin, KELVIN))


def _neumann(region_id: str, flux: float = 0.0, name: str | None = None):
    return FieldBoundaryCondition(
        name=name or f"flux-{region_id}", field_id="T", region_id=region_id,
        kind=BoundaryKind.NEUMANN, value=Quantity(flux, FLUX))


def _duplicate_left(mesh: StructuredMesh) -> MeshRegion:
    """A second region on LEFT, under a name of its own -- which is all it takes."""
    return MeshRegion(
        region_id=f"{mesh.mesh_id}:left-flux", mesh_id=mesh.mesh_id, edge=BoundaryEdge.LEFT,
        description="a second region claiming the left edge")


# =====================================================================
# R-56: the core gate keys by edge, not by the name a caller chose
# =====================================================================
def test_r56_two_conditions_on_one_edge_under_two_region_ids_are_refused():
    """Both at the SAME value, so nothing else in the layer has a reason to object.

    At DIFFERENT values the corner-agreement rule happens to catch this pair -- the two conditions
    prescribe 300 and 400 K at the corner they share -- which is a true finding about corners and
    says nothing about the edge. Two conditions on one edge is a contradiction whatever they
    prescribe: only one of them is imposed, and which one is an iteration order.
    """
    mesh = _mesh()
    regions = (*boundary_regions(mesh), _duplicate_left(mesh))
    conditions = [_dirichlet(r.region_id) for r in boundary_regions(mesh)]
    conditions.append(_dirichlet(f"{mesh.mesh_id}:left-flux", kelvin=300.0, name="the-second-one"))
    with pytest.raises(InvalidScientificProblem, match="One edge, one condition"):
        require_complete_boundary(_field(mesh), mesh, regions, conditions)


def test_r56_a_dirichlet_and_a_neumann_on_one_edge_are_refused():
    """The corner check only compares Dirichlet pairs, so this went through untouched."""
    mesh = _mesh()
    regions = (*boundary_regions(mesh), _duplicate_left(mesh))
    conditions = [_dirichlet(r.region_id) for r in boundary_regions(mesh)]
    conditions.append(_neumann(f"{mesh.mesh_id}:left-flux"))
    with pytest.raises(InvalidScientificProblem, match="One edge, one condition"):
        require_complete_boundary(_field(mesh), mesh, regions, conditions)


def test_r56_a_region_set_that_misses_an_edge_is_not_a_complete_boundary():
    """`one of four edges conditioned, regions=(left,): ACCEPTED as complete`, and then a KeyError."""
    mesh = _mesh()
    left = boundary_regions(mesh)[0]
    with pytest.raises(InvalidScientificProblem, match="under-determined"):
        require_complete_boundary(_field(mesh), mesh, (left,), [_dirichlet(left.region_id)])


def test_r56_the_refusal_names_the_edges_that_have_no_condition():
    """Region ids the caller chose, so only an EDGE-keyed message can name what is missing.

    `boundary_regions` derives its ids from the edge, which is why the old region-id message read as
    though it named edges. These four do not, so the assertion is about the rule and not the naming.
    """
    mesh = _mesh()
    named = {
        BoundaryEdge.LEFT: "alpha", BoundaryEdge.RIGHT: "beta",
        BoundaryEdge.BOTTOM: "gamma", BoundaryEdge.TOP: "delta",
    }
    regions = tuple(
        MeshRegion(region_id=name, mesh_id=mesh.mesh_id, edge=edge)
        for edge, name in named.items()
    )
    with pytest.raises(InvalidScientificProblem) as caught:
        require_complete_boundary(
            _field(mesh), mesh, regions,
            [_dirichlet(named[BoundaryEdge.LEFT]), _dirichlet(named[BoundaryEdge.RIGHT])])
    message = str(caught.value)
    assert BoundaryEdge.BOTTOM.value in message and BoundaryEdge.TOP.value in message, message


def test_r56_a_boundary_conditioned_once_per_edge_is_still_complete():
    """No-regression: the shape every in-tree caller uses."""
    mesh = _mesh()
    regions = boundary_regions(mesh)
    require_complete_boundary(
        _field(mesh), mesh, regions, [_dirichlet(r.region_id) for r in regions])


# =====================================================================
# R-56: the consumer that actually chose the winner
# =====================================================================
def test_r56_the_problems_edge_map_refuses_a_collision_instead_of_choosing_a_winner():
    """`edges` is a public property, and a caller may hold a problem the core gate did not build.

    The duplicate is injected after construction on purpose: with the gate above in place a problem
    carrying one cannot be built, and this is a test of the consumer's own guard.
    """
    mesh = _mesh()
    problem = plate_problem(
        problem_id="collision", mesh=mesh, conductivity=CONDUCTIVITY,
        edge_values={edge: Quantity(300.0, KELVIN) for edge in BoundaryEdge})
    object.__setattr__(problem, "regions", (*problem.regions, _duplicate_left(mesh)))
    object.__setattr__(
        problem, "conditions",
        (*problem.conditions, _neumann(f"{mesh.mesh_id}:left-flux", name="injected")))
    with pytest.raises(Exception, match="(?i)one edge, one condition|left"):
        problem.edges


# =====================================================================
# R-56: the audited end-to-end case
# =====================================================================
def test_r56_the_audited_conduction_case_is_refused_rather_than_silently_solved():
    """9x9 plate, 400 K on `plate:left`, 0 W/m^2 on a second region claiming the same edge.

    Before: every check PASS and a field maximum of 300.00000000019827 K, with the 400 K edge
    declared in `problem.conditions` and imposed nowhere.
    """
    mesh = _mesh()
    field = _field(mesh)
    regions = (*boundary_regions(mesh), _duplicate_left(mesh))
    by_edge = {region.edge: region for region in boundary_regions(mesh)}
    conditions = (
        _dirichlet(by_edge[BoundaryEdge.LEFT].region_id, kelvin=400.0, name="left_hot"),
        _neumann(f"{mesh.mesh_id}:left-flux", name="left_insulated"),
        _dirichlet(by_edge[BoundaryEdge.RIGHT].region_id, kelvin=300.0, name="right_cold"),
        _neumann(by_edge[BoundaryEdge.BOTTOM].region_id, name="bottom"),
        _neumann(by_edge[BoundaryEdge.TOP].region_id, name="top"),
    )
    with pytest.raises(Exception, match="(?i)one edge, one condition"):
        SteadyConductionProblem(
            problem_id="audited-duplicate", mesh=mesh, field=field,
            conductivity=CONDUCTIVITY, conditions=conditions, regions=regions)


def test_r56_the_same_plate_declared_once_per_edge_imposes_its_400_kelvin_edge():
    """The honest counterpart, and the number the audited run should have produced."""
    mesh = _mesh()
    problem = plate_problem(
        problem_id="honest", mesh=mesh, conductivity=CONDUCTIVITY,
        edge_values={
            BoundaryEdge.LEFT: Quantity(400.0, KELVIN),
            BoundaryEdge.RIGHT: Quantity(300.0, KELVIN),
            BoundaryEdge.BOTTOM: Quantity(0.0, FLUX),
            BoundaryEdge.TOP: Quantity(0.0, FLUX),
        },
        edge_kinds={BoundaryEdge.BOTTOM: BoundaryKind.NEUMANN,
                    BoundaryEdge.TOP: BoundaryKind.NEUMANN})
    solved = solve_steady_conduction(problem, run_id="honest").values
    assert np.isclose(float(np.max(solved.values)), 400.0, atol=1e-6)
    assert np.isclose(float(np.min(solved.values)), 300.0, atol=1e-6)
