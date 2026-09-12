"""The vertical slice: a field problem declared, solved, recorded and read back.

Sprint 4, Phases 7, 10, 11, 14 and 15. What is asserted here is not that the
numbers are close to something — the convergence study does that — but that the
scientific structure survives the round trip: the support, the unit, the shape,
the boundary data and the refusals are all in records a reader can check, and
none of them is a label, a comment or an array in a metadata slot.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.data.field import FieldValue
from engcore.data.resolver import BulkDataResolver
from engcore.data.store import InMemoryBulkStore
from engcore.domains.thermal_models.conduction2d import (
    APPLICABILITY,
    SOLVER_ID,
    Conduction2DError,
    SteadyConductionProblem,
    node_grid,
    plate_problem,
    solve_steady_conduction,
)
from engcore.scientific.fields import (
    BoundaryEdge,
    FieldBoundaryCondition,
    FieldDefinition,
    FieldLocation,
    FieldRecord,
    StructuredMesh,
    boundary_regions,
)
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.solvers.protocol import ConvergenceState
from engcore.scientific.units.quantity import Quantity
from tests.manufactured_conduction2d import SINE_PLATE, square

CONDUCTIVITY = Quantity(2.5, "watt/meter/kelvin")


def plate(nodes: int = 9, **changes) -> SteadyConductionProblem:
    mesh = changes.pop("mesh", None) or square(nodes)
    return plate_problem(
        problem_id=changes.pop("problem_id", "plate"),
        mesh=mesh,
        conductivity=changes.pop("conductivity", CONDUCTIVITY),
        edge_values=changes.pop(
            "edge_values", {edge: Quantity(300.0, "kelvin") for edge in BoundaryEdge}
        ),
        **changes,
    )


# ---- the discretisation reproduces what it must ------------------------------------
def test_a_uniform_dirichlet_plate_is_uniform():
    """No source, one temperature all round: every interior node is that value."""
    solved = solve_steady_conduction(plate(), run_id="uniform").values
    assert np.allclose(solved.values, 300.0, atol=1e-9)


def test_a_linear_profile_is_reproduced_exactly():
    """A 5-point stencil is exact on a linear field; insulated sides must not spoil it."""
    mesh = square(11)
    problem = plate_problem(
        problem_id="linear",
        mesh=mesh,
        conductivity=CONDUCTIVITY,
        edge_values={
            BoundaryEdge.LEFT: Quantity(300.0, "kelvin"),
            BoundaryEdge.RIGHT: Quantity(400.0, "kelvin"),
            BoundaryEdge.BOTTOM: Quantity(0.0, "watt/meter**2"),
            BoundaryEdge.TOP: Quantity(0.0, "watt/meter**2"),
        },
        edge_kinds={
            BoundaryEdge.BOTTOM: BoundaryKind.NEUMANN,
            BoundaryEdge.TOP: BoundaryKind.NEUMANN,
        },
    )
    solved = solve_steady_conduction(problem, run_id="linear").values
    x, _ = node_grid(mesh)
    assert np.max(np.abs(solved.values - (300.0 + 100.0 * x))) < 1e-9


def test_a_non_square_support_is_not_transposed():
    """The classic silent failure: 33 x 17 solved as 17 x 33 and nobody notices."""
    mesh = StructuredMesh("wide", Quantity(2.0, "meter"), Quantity(1.0, "meter"), 33, 17)
    solved = solve_steady_conduction(plate(mesh=mesh), run_id="wide").values
    assert solved.shape == (17, 33)
    assert solved.values.shape == solved.definition.expected_shape(mesh)


# ---- what the result says ------------------------------------------------------------
def test_the_result_carries_scalar_evidence_and_a_reference_not_an_array():
    solution = solve_steady_conduction(plate(33), run_id="evidence")
    result = solution.result

    assert set(result.values) == {"T:min", "T:max", "T:mean", "T:l2_norm"}
    assert all(isinstance(value, Quantity) for value in result.values.values())
    assert result.values["T:max"].units == "kelvin"

    (reference,) = result.data_references
    assert reference.count == 33 * 33
    assert reference.unit == "kelvin"
    assert reference.digest == solution.field.reference.digest

    payload = result.to_dict()
    assert len(str(payload)) < 6000, "a result stays small however large the field is"
    assert "300.0, 300.0" not in str(payload), "the values themselves must not be inline"


def test_the_result_does_not_claim_convergence_for_a_direct_solve():
    result = solve_steady_conduction(plate(), run_id="direct").result
    assert result.convergence is ConvergenceState.NOT_APPLICABLE
    assert result.solver.solver_id == SOLVER_ID


def test_the_validation_report_states_what_was_checked():
    report = solve_steady_conduction(plate(), run_id="checks").result.validation
    names = {check.name for check in report.checks}
    assert names == {
        "field_finite",
        "field_linear_system_residual",
        "boundary_conditions_held",
    }
    assert all(check.outcome.value == "pass" for check in report.checks)
    residual = next(c for c in report.checks if c.name == "field_linear_system_residual")
    assert residual.residual is not None and residual.tolerance is not None


def test_the_provenance_records_the_support_and_the_envelope():
    provenance = solve_steady_conduction(plate(), run_id="prov").result.provenance
    assert provenance.assumptions == APPLICABILITY
    assert provenance.inputs["conductivity"] == CONDUCTIVITY
    assert provenance.metadata["mesh_fingerprint"] == square(9).fingerprint()


# ---- serialization -------------------------------------------------------------------
def test_a_result_round_trips_and_still_names_the_same_bytes():
    solution = solve_steady_conduction(plate(17), run_id="round-trip")
    restored = ScientificResult.from_dict(solution.result.to_dict())
    assert restored == solution.result
    assert restored.data_references[0].digest == solution.field.reference.digest


def test_a_field_record_round_trips_and_the_values_are_recovered_through_it():
    solution = solve_steady_conduction(plate(17), run_id="field-round-trip")
    restored = FieldRecord.from_dict(solution.field.to_dict())
    assert restored == solution.field

    read_back = FieldValue.from_record(
        restored, square(17), BulkDataResolver(solution.store)
    )
    assert read_back == solution.values


def test_a_record_deserialized_against_the_wrong_support_is_refused():
    """FM-8: the bytes resolve and the length agrees; the meaning does not."""
    solution = solve_steady_conduction(plate(17), run_id="wrong-support")
    resolver = BulkDataResolver(solution.store)
    with pytest.raises(Exception, match="different geometry|does not"):
        FieldValue.from_record(
            solution.field, square(17, length=2.0), resolver
        )


# ---- the envelope refuses, by name ----------------------------------------------------
@pytest.mark.parametrize(
    "changes, expected",
    [
        (dict(conductivity=(1.0, 2.0)), "isotropic"),
        (dict(conductivity=lambda t: t), "constant"),
        (dict(conductivity=Quantity(-1.0, "watt/meter/kelvin")), "strictly positive"),
        (dict(conductivity=Quantity(0.0, "watt/meter/kelvin")), "strictly positive"),
        (dict(conductivity=2.5), "must be a Quantity"),
        (dict(conductivity=Quantity(2.5, "watt")), "dimension"),
        (dict(field_unit="volt"), "dimension"),
        (dict(source=Quantity(1.0, "kelvin")), "dimension"),
        (dict(source=object()), "a Quantity, a SpatialProfile or a FieldValue"),
    ],
)
def test_a_request_outside_the_envelope_is_refused(changes, expected):
    with pytest.raises(Conduction2DError, match=expected):
        plate(**changes)


def test_a_field_at_the_cells_is_refused_rather_than_silently_moved():
    mesh = square(9)
    with pytest.raises(Conduction2DError, match="nodes"):
        SteadyConductionProblem(
            problem_id="cells",
            mesh=mesh,
            field=FieldDefinition("T", "kelvin", mesh.mesh_id, location=FieldLocation.CELL),
            conductivity=CONDUCTIVITY,
            conditions=(),
        )


def test_a_vector_field_is_refused():
    mesh = square(9)
    with pytest.raises(Conduction2DError, match="one scalar field"):
        SteadyConductionProblem(
            problem_id="vector",
            mesh=mesh,
            field=FieldDefinition("q", "kelvin", mesh.mesh_id, components=2),
            conductivity=CONDUCTIVITY,
            conditions=(),
        )


@pytest.mark.parametrize(
    "kind, extra",
    [
        (
            BoundaryKind.ROBIN,
            dict(
                value=Quantity(300.0, "kelvin"),
                coefficients={"h": Quantity(5.0, "watt/meter**2/kelvin")},
            ),
        ),
        (BoundaryKind.PERIODIC, {}),
    ],
)
def test_a_boundary_family_this_model_does_not_serve_is_refused(kind, extra):
    """Representable in the core records, and not served here. Two different facts.

    The condition below is well-formed — a robin condition carrying the
    coefficients that make it one — so what refuses it is this model's
    envelope and not the declaration layer rejecting a malformed record.
    """
    mesh = square(9)
    regions = boundary_regions(mesh)
    conditions = []
    for region in regions:
        if region.edge is BoundaryEdge.TOP:
            conditions.append(
                FieldBoundaryCondition(
                    name="T-top", field_id="T", region_id=region.region_id,
                    kind=kind, **extra,
                )
            )
            continue
        conditions.append(
            FieldBoundaryCondition(
                name=f"T-{region.edge.value}", field_id="T",
                region_id=region.region_id, kind=BoundaryKind.DIRICHLET,
                value=Quantity(300.0, "kelvin"),
            )
        )
    with pytest.raises(Conduction2DError, match="dirichlet and neumann only"):
        SteadyConductionProblem(
            problem_id="unserved",
            mesh=mesh,
            field=FieldDefinition("T", "kelvin", mesh.mesh_id),
            conductivity=CONDUCTIVITY,
            conditions=tuple(conditions),
        )


def test_an_edge_with_no_condition_is_refused_as_under_determined():
    values = {edge: Quantity(300.0, "kelvin") for edge in BoundaryEdge}
    del values[BoundaryEdge.TOP]
    with pytest.raises(Exception, match="under-determined|top"):
        plate(edge_values=values)


def test_two_conditions_on_one_edge_are_refused():
    mesh = square(9)
    regions = boundary_regions(mesh)
    left = next(region for region in regions if region.edge is BoundaryEdge.LEFT)
    conditions = [
        FieldBoundaryCondition(
            name=f"T-{region.edge.value}",
            field_id="T",
            region_id=region.region_id,
            kind=BoundaryKind.DIRICHLET,
            value=Quantity(300.0, "kelvin"),
        )
        for region in regions
    ]
    conditions.append(
        FieldBoundaryCondition(
            name="T-left-again",
            field_id="T",
            region_id=left.region_id,
            kind=BoundaryKind.DIRICHLET,
            value=Quantity(400.0, "kelvin"),
        )
    )
    with pytest.raises(Exception, match="one condition|duplicate"):
        SteadyConductionProblem(
            problem_id="doubled",
            mesh=mesh,
            field=FieldDefinition("T", "kelvin", mesh.mesh_id),
            conductivity=CONDUCTIVITY,
            conditions=tuple(conditions),
        )


def test_an_all_flux_plate_is_refused_as_singular_rather_than_solved():
    """Every edge insulated leaves the level free; the matrix is singular."""
    with pytest.raises(Conduction2DError, match="singular|up to a constant"):
        plate(
            edge_values={edge: Quantity(0.0, "watt/meter**2") for edge in BoundaryEdge},
            edge_kinds={edge: BoundaryKind.NEUMANN for edge in BoundaryEdge},
        )


def test_a_source_on_another_support_is_refused():
    other = square(9, mesh_id="other", length=3.0)
    source = FieldValue(
        FieldDefinition("q", "watt/meter**3", other.mesh_id),
        other,
        np.zeros((9, 9)),
    )
    with pytest.raises(Conduction2DError, match="support"):
        plate(source=source)


def test_a_field_declared_on_another_support_is_refused():
    mesh = square(9)
    with pytest.raises(Exception, match="is not a field of another|support"):
        SteadyConductionProblem(
            problem_id="elsewhere",
            mesh=mesh,
            field=FieldDefinition("T", "kelvin", "somewhere-else"),
            conductivity=CONDUCTIVITY,
            conditions=(),
        )


# ---- the source actually does something ------------------------------------------------
def test_a_source_raises_the_interior_above_its_boundary():
    """Sanity, not accuracy: heat generated inside a cooled plate makes it hotter."""
    mesh = square(17)
    problem = SINE_PLATE.problem(mesh)
    solved = solve_steady_conduction(problem, run_id="source").values
    assert solved.values.max() > 300.0 + 1.0
    edges = np.concatenate(
        [solved.values[0, :], solved.values[-1, :], solved.values[:, 0], solved.values[:, -1]]
    )
    assert np.allclose(edges, 300.0, atol=1e-9), "the boundary is still what was asked for"


def test_the_stored_field_is_the_field_that_was_solved():
    solution = solve_steady_conduction(plate(17), run_id="identity")
    read_back = FieldValue.from_record(
        solution.field, square(17), BulkDataResolver(InMemoryBulkStore(), solution.store)
    )
    assert np.array_equal(read_back.values, solution.values.values)
    assert solution.field.summary.maximum == solution.values.summary().maximum
