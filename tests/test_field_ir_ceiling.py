"""What the scalar IR cannot say about a field, demonstrated rather than asserted.

Sprint 4, Phase 1. Before adding any type, this records what the current
representation does when handed a spatial field — the ceiling the field layer
has to clear, in executable form.

The scalar IR is not wrong. It is a *scalar* IR, and every refusal below is it
working correctly: a bare array is not a scientific value, and letting one into
`values` would be the untyped escape hatch this platform refuses everywhere
else. What the refusals establish is that ``T(x, y)`` has nowhere to live, and
what the last two tests establish is what that costs in production today: the
one solved field this repository computes travels in an anonymous diagnostics
entry, and the bulk-data identity that names it knows a *count* and not a shape.

These tests stay true after the field layer lands. They are the statement of
where the scalar path ends, not a defect list.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.domains.thermal.conduction1d.problem import (
    ConductionSlab,
    SlabDiscretization,
    build_conduction_problem,
)
from engcore.domains.thermal.conduction1d.solver import Conduction1DSolver
from engcore.scientific.composition.dependency import QuantityDependency
from engcore.scientific.composition.transfer import QuantityTransfer
from engcore.scientific.errors import InvalidScientificProblem, ScientificCoreError
from engcore.scientific.ir.conditions import (
    BoundaryCondition,
    BoundaryKind,
    InitialCondition,
)
from engcore.scientific.ir.problem import ScientificProblem
from engcore.scientific.ir.values import require_scientific_value
from engcore.scientific.ir.variables import ScientificVariable
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.units.quantity import Quantity

#: One temperature field on a 4x4 grid, as a solver would produce it.
FIELD = np.linspace(300.0, 400.0, 16)


# ---- 1. a field is not a scientific value -------------------------------------------
def test_a_field_cannot_be_a_quantity():
    """`Quantity` is a magnitude and a unit. An array is neither."""
    with pytest.raises(TypeError):
        Quantity(FIELD, "kelvin")


def test_a_field_is_not_a_member_of_the_typed_value_union():
    with pytest.raises(InvalidScientificProblem, match="typed scientific value"):
        require_scientific_value(FIELD, context="temperature field")


def test_an_initial_field_cannot_be_declared():
    """T(x, y, 0) has nowhere to go: an initial condition holds one Quantity."""
    with pytest.raises(InvalidScientificProblem, match="requires a Quantity value"):
        InitialCondition(variable="T", value=FIELD)


def test_a_result_cannot_carry_a_field_value():
    with pytest.raises(ScientificCoreError, match="must be a Quantity"):
        ScientificResult(
            result_id="r",
            values={"T": FIELD},
            provenance=ProvenanceRecord(run_id="ceiling"),
        )


def test_a_variable_declares_no_shape_no_location_and_no_mesh():
    """The whole vocabulary of a field variable is absent, not merely unused."""
    declared = set(ScientificVariable("T", "kelvin").__dataclass_fields__)
    assert declared == {
        "name", "unit", "kind", "role", "lower", "upper", "categories", "description",
    }
    for absent in ("shape", "components", "location", "mesh", "mesh_id", "support"):
        assert absent not in declared


# ---- 2. a region is a label, and the core says so ---------------------------------------
def test_a_boundary_region_is_an_uninterpreted_string():
    """Nothing resolves ``region`` against geometry, because there is no geometry.

    The core's own docstring says it: the region is "an opaque label owned by
    the domain". That is a sound decision for a scalar IR with no mesh, and it
    is exactly what a field problem cannot accept — a Dirichlet condition on
    ``left`` has to mean a definite set of nodes.
    """
    nonsense = BoundaryCondition(
        name="bc", variable="T", kind=BoundaryKind.NEUMANN,
        region="northeast-ish", value=Quantity(1.0, "watt/meter**2"),
    )
    assert nonsense.region == "northeast-ish"

    # ...and it is accepted by a problem that declares no geometry at all.
    problem = ScientificProblem(
        problem_id="no-geometry",
        variables=(ScientificVariable("T", "kelvin"),),
        boundary_conditions=(nonsense,),
    )
    assert problem.boundary_conditions[0].region == "northeast-ish"
    assert not any("mesh" in f for f in problem.__dataclass_fields__)


def test_two_problems_of_different_geometry_accept_the_same_region_label():
    """`left` is one string. Which nodes it names is nowhere stated."""
    def problem_with(problem_id: str, extent_m: float) -> ScientificProblem:
        return ScientificProblem(
            problem_id=problem_id,
            variables=(ScientificVariable("T", "kelvin"),),
            boundary_conditions=(
                BoundaryCondition(
                    name="hot", variable="T", kind=BoundaryKind.DIRICHLET,
                    region="left", value=Quantity(400.0, "kelvin"),
                ),
            ),
            # The only place a size could be stated is untyped metadata.
            metadata={"width_m": extent_m},
        )

    narrow, wide = problem_with("narrow", 0.1), problem_with("wide", 10.0)
    assert narrow.boundary_conditions[0] == wide.boundary_conditions[0]


# ---- 3. bulk identity knows a count, not a shape --------------------------------------
def test_a_data_reference_cannot_distinguish_two_shapes_of_one_array():
    """16 values are 16 values: a 4x4 field and a 2x8 field share one identity.

    This is the documented boundary of DATA-BOUNDARY0, which says so in its own
    module docstring: ``count`` "is a count of values and is *not* a shape", and
    mesh, topology and field support are deferred. The field layer is what has
    to supply them.
    """
    square, _ = ScientificDataReference.for_values("T:field", FIELD.tolist(), unit="kelvin")
    strip, _ = ScientificDataReference.for_values("T:field", FIELD.tolist(), unit="kelvin")
    assert square == strip
    assert square.count == 16
    declared = set(square.__dataclass_fields__)
    assert declared == {"name", "unit", "count", "dtype", "digest", "digest_algorithm"}
    for absent in ("shape", "mesh", "mesh_id", "location", "components"):
        assert absent not in declared


# ---- 4. what that costs in production, today ------------------------------------------
def test_the_one_solved_field_in_this_repository_travels_in_diagnostics():
    """The frozen 1-D conduction solver has nowhere else to put it.

    ``raw.values`` is ``Mapping[str, float]``, so the four scalar summaries fit
    and the field does not. It goes into ``diagnostics``, an anonymous
    ``Mapping[str, Any]`` carrying no unit, no shape and no mesh — which is why
    ``conduction1d_bulk`` exists to lift it back out into a typed reference.
    """
    slab = ConductionSlab(
        slab_id="S", length=Quantity(1.0, "meter"),
        diffusivity=Quantity(1e-4, "meter**2/second"),
        end_time=Quantity(1.0, "second"),
        discretization=SlabDiscretization(8, 4),
    )
    problem = build_conduction_problem(slab)
    solver = Conduction1DSolver()
    solver.bind_slab(slab, problem.problem_id)
    raw = solver.solve(solver.prepare(problem))

    assert all(isinstance(v, float) for v in raw.values.values())
    assert "field" not in raw.values

    field = raw.diagnostics["field"]
    assert len(field) == 9
    assert all(isinstance(v, float) for v in field)
    # The channel it arrived in states none of what a field is:
    assert not any(key in raw.diagnostics for key in ("field_unit", "mesh", "shape"))


# ---- 5. composition transports a scalar ------------------------------------------------
def test_a_declared_crossing_can_only_carry_one_scalar():
    """The transfer record realizes a dependency with a `Quantity`.

    A temperature field crossing to a downstream consumer has no representation
    here: not as a value, and not as a declaration of what shape or mesh the
    consumer should expect.
    """
    dependency = QuantityDependency(
        source_problem_id="upstream",
        source_quantity="T:field",
        target_problem_id="downstream",
        target_quantity="T:inlet",
        unit_exemplar="kelvin",
    )
    with pytest.raises(InvalidScientificProblem, match="Quantity"):
        QuantityTransfer(
            dependency=dependency,
            value=FIELD,
            source_record_id="upstream-run",
            instant="step-1",
        )

    # The scalar crossing it was built for is accepted, and says nothing about
    # a mesh, a location or a shape on either side.
    crossing = QuantityTransfer(
        dependency=dependency,
        value=Quantity(350.0, "kelvin"),
        source_record_id="upstream-run",
        instant="step-1",
    )
    assert crossing.value == Quantity(350.0, "kelvin")
    assert not any(
        key in crossing.to_dict() for key in ("mesh", "shape", "location", "support")
    )
