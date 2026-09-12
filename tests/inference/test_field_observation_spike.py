"""B9: the inference stack can consume a scalar derived from a field.

The claim under test is narrow and the boundary matters:

    an observation operator is declared in the units of the WORLD, and the
    array index is derived from whichever mesh it is applied to

and therefore

    the same array index on a different mesh is NOT automatically the same
    observation.

No PDE is calibrated here. This is a spike.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.inference.field_observation import (
    FieldObservationError,
    FieldObservationKind,
    FieldObservationOperator,
)
from engcore.scientific.fields.mesh import StructuredMesh
from engcore.scientific.fields.regions import BoundaryEdge, MeshRegion, boundary_regions
from engcore.scientific.units.quantity import Quantity

METER, KELVIN = "meter", "kelvin"


def mesh(nodes_x=5, nodes_y=5, mesh_id="plate"):
    return StructuredMesh(
        mesh_id=mesh_id,
        length_x=Quantity(0.04, METER),
        length_y=Quantity(0.04, METER),
        nodes_x=nodes_x,
        nodes_y=nodes_y,
    )


def ramp(m: StructuredMesh) -> np.ndarray:
    """T(x, y) = 300 + 1000*x + 500*y, evaluated on the mesh's own nodes.

    An analytic field, so the value at a physical location is known
    independently of any discretisation -- which is what lets the tests below
    say what the right answer IS rather than comparing two implementations.
    """
    xs, ys = m.axis_coordinates()
    out = np.empty(m.node_count, dtype=np.float64)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            out[m.node_index(i, j)] = 300.0 + 1000.0 * x + 500.0 * y
    return out


def probe_at(m, x=0.02, y=0.01, operator_id="probe.centre"):
    return FieldObservationOperator(
        operator_id=operator_id,
        kind=FieldObservationKind.PROBE_AT_LOCATION,
        field_id="temperature",
        mesh_fingerprint=m.fingerprint(),
        unit=KELVIN,
        probe_x=Quantity(x, METER),
        probe_y=Quantity(y, METER),
        description="declared thermocouple location",
    )


# =====================================================================
# The operator is explicit and serializable
# =====================================================================

def test_a_probe_is_declared_by_location_and_round_trips():
    m = mesh()
    operator = probe_at(m)
    payload = operator.to_dict()

    assert payload["kind"] == "probe_at_location"
    assert payload["probe_x"] == 0.02 and payload["probe_y"] == 0.01
    assert "index" not in payload and "i" not in payload and "j" not in payload

    restored = FieldObservationOperator.from_dict(payload)
    assert restored.digest == operator.digest


def test_an_edited_operator_is_refused_on_read():
    m = mesh()
    payload = dict(probe_at(m).to_dict())
    payload["probe_x"] = 0.03
    with pytest.raises(FieldObservationError, match="digest"):
        FieldObservationOperator.from_dict(payload)


def test_a_probe_without_a_location_is_refused():
    m = mesh()
    with pytest.raises(FieldObservationError, match="physical LOCATIONS"):
        FieldObservationOperator(
            operator_id="bad",
            kind=FieldObservationKind.PROBE_AT_LOCATION,
            field_id="temperature",
            mesh_fingerprint=m.fingerprint(),
            unit=KELVIN,
        )


def test_a_mesh_id_is_not_accepted_as_a_support_identity():
    """A label will not do: two discretisations routinely share a mesh_id."""
    with pytest.raises(FieldObservationError, match="by fingerprint"):
        FieldObservationOperator(
            operator_id="bad",
            kind=FieldObservationKind.FIELD_MAXIMUM,
            field_id="temperature",
            mesh_fingerprint="plate",
            unit=KELVIN,
        )


# =====================================================================
# THE CLAIM -- an index is not an identity
# =====================================================================

def test_the_same_array_index_on_a_different_mesh_is_a_different_place():
    """Stated as physics before it is stated as a refusal.

    Node (2, 2) of a 5x5 mesh over 40 mm is the centre, x = 20 mm. Node (2, 2)
    of a 9x9 mesh over the same extent is x = 10 mm. Same integers, different
    place, different temperature -- and an operator recorded as `field[2, 2]`
    would have reported both as the same measurement.
    """
    coarse, fine = mesh(5, 5), mesh(9, 9)
    coarse_xs, _ = coarse.axis_coordinates()
    fine_xs, _ = fine.axis_coordinates()

    assert coarse_xs[2] == pytest.approx(0.02)
    assert fine_xs[2] == pytest.approx(0.01)

    index = coarse.node_index(2, 2)
    assert ramp(coarse)[index] != pytest.approx(ramp(fine)[fine.node_index(2, 2)])


def test_an_operator_refuses_a_support_it_was_not_declared_against():
    coarse, fine = mesh(5, 5), mesh(9, 9)
    operator = probe_at(coarse)
    with pytest.raises(FieldObservationError, match="different physical place"):
        operator.apply(fine, ramp(fine))


def test_the_same_physical_probe_on_two_meshes_reads_the_same_temperature():
    """The converse, and the reason declaring a LOCATION is the right fix.

    Re-declare the same physical probe against the refined support and it finds
    the same place and the same value -- because the location was the identity
    and the index was always derived. That is the property `field[i, j]` cannot
    have.
    """
    coarse, fine = mesh(5, 5), mesh(9, 9)
    got_coarse = probe_at(coarse).apply(coarse, ramp(coarse))
    got_fine = probe_at(fine).apply(fine, ramp(fine))

    expected = 300.0 + 1000.0 * 0.02 + 500.0 * 0.01
    assert got_coarse.magnitude_in(KELVIN) == pytest.approx(expected)
    assert got_fine.magnitude_in(KELVIN) == pytest.approx(expected)


def test_the_two_operators_are_not_the_same_record():
    """Same location, different support -> different operator, by digest."""
    assert probe_at(mesh(5, 5)).digest != probe_at(mesh(9, 9)).digest


def test_a_probe_between_nodes_reports_how_far_it_snapped():
    """A snapped probe is measuring somewhere else, and says so."""
    m = mesh(5, 5)  # nodes every 10 mm
    operator = probe_at(m, x=0.015, y=0.015, operator_id="probe.between")
    offset = operator.probe_offset(m)
    assert offset.magnitude_in(METER) > 0.0
    assert offset.magnitude_in(METER) == pytest.approx(np.hypot(0.005, 0.005))


# =====================================================================
# The other two kinds
# =====================================================================

def test_a_region_mean_is_taken_over_a_declared_region():
    m = mesh(5, 5)
    region = next(r for r in boundary_regions(m) if r.edge is BoundaryEdge.LEFT)
    operator = FieldObservationOperator(
        operator_id="mean.left",
        kind=FieldObservationKind.REGION_MEAN,
        field_id="temperature",
        mesh_fingerprint=m.fingerprint(),
        unit=KELVIN,
        region_id=region.region_id,
    )
    got = operator.apply(m, ramp(m), region=region)
    # left edge is x = 0, so T = 300 + 500*y averaged over y in [0, 0.04]
    assert got.magnitude_in(KELVIN) == pytest.approx(300.0 + 500.0 * 0.02)


def test_a_region_mean_refuses_a_region_it_did_not_name():
    m = mesh(5, 5)
    regions = {r.edge: r for r in boundary_regions(m)}
    operator = FieldObservationOperator(
        operator_id="mean.left",
        kind=FieldObservationKind.REGION_MEAN,
        field_id="temperature",
        mesh_fingerprint=m.fingerprint(),
        unit=KELVIN,
        region_id=regions[BoundaryEdge.LEFT].region_id,
    )
    with pytest.raises(FieldObservationError, match="names region"):
        operator.apply(m, ramp(m), region=regions[BoundaryEdge.RIGHT])


def test_a_field_maximum_is_over_the_whole_support_and_says_so():
    m = mesh(5, 5)
    operator = FieldObservationOperator(
        operator_id="max.plate",
        kind=FieldObservationKind.FIELD_MAXIMUM,
        field_id="temperature",
        mesh_fingerprint=m.fingerprint(),
        unit=KELVIN,
    )
    assert operator.apply(m, ramp(m)).magnitude_in(KELVIN) == pytest.approx(
        300.0 + 1000.0 * 0.04 + 500.0 * 0.04
    )
    with pytest.raises(FieldObservationError, match="neither probe nor region"):
        FieldObservationOperator(
            operator_id="bad",
            kind=FieldObservationKind.FIELD_MAXIMUM,
            field_id="temperature",
            mesh_fingerprint=m.fingerprint(),
            unit=KELVIN,
            probe_x=Quantity(0.0, METER),
            probe_y=Quantity(0.0, METER),
        )


# =====================================================================
# It feeds the inference stack
# =====================================================================

def test_the_scalar_feeds_a_gaussian_observation_unchanged():
    """The spike's actual point: what comes out is an ordinary observation."""
    from engcore.inference.grid import GaussianObservation, ObservationSet

    m = mesh(5, 5)
    operator = probe_at(m)
    value = operator.apply(m, ramp(m))
    observation = GaussianObservation(
        condition_id="probe.centre",
        observable_name=operator.field_id,
        value=value,
        sigma=Quantity(0.5, KELVIN),
        source_ref=f"operator:{operator.operator_id}@{operator.digest[:12]}",
    )
    observations = ObservationSet((observation,), dataset_id="field.spike")
    assert observations.keys == ("probe.centre:temperature",)
    assert observation.value.magnitude_in(KELVIN) == pytest.approx(325.0)


def test_a_non_finite_field_cannot_produce_an_interpreted_scalar():
    m = mesh(5, 5)
    values = ramp(m)
    values[3] = float("nan")
    with pytest.raises(FieldObservationError, match="non-finite"):
        probe_at(m).apply(m, values)


def test_a_field_of_the_wrong_size_is_refused():
    m = mesh(5, 5)
    with pytest.raises(FieldObservationError, match="value\\(s\\) for a support"):
        probe_at(m).apply(m, np.zeros(7))
