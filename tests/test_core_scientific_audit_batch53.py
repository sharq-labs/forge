"""Core re-audit 2026-09-16, batch 53: two gates that never re-derive what they assert.

Problems R-63 (the audit's finding 77) and R-73 (finding 104), improvement I-25 part B of two, under
benchmarks/core_v4_false_confidence/BATCH53_THRESHOLD_PROTOCOL.json.

`FieldTransferContract` carries both field definitions AND a verdict, and checks the types, the fingerprint
format and a non-empty reason -- so a payload computed as REFUSED for 1 component against 3, kelvin against
pascal, reads back as COMPATIBLE with `may_cross_directly` True. `FieldObservationOperator` says an
observation is identified by CONTENT rather than by an index, and identifies its region by LABEL: the same
operator and digest return the mean of the left edge or the right edge depending on which region object is
handed over. And a probe declared metres away from a 10 mm plate silently reads a corner node.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from engcore.inference.field_observation import (
    FieldObservationError,
    FieldObservationKind,
    FieldObservationOperator,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields.definition import FieldDefinition, FieldLocation
from engcore.scientific.fields.mesh import StructuredMesh
from engcore.scientific.fields.regions import BoundaryEdge, MeshRegion
from engcore.scientific.fields.transfer import (
    FieldTransferContract,
    FieldTransferVerdict,
    TransferKind,
    check_field_transfer,
)
from engcore.scientific.units.quantity import Quantity

METER, KELVIN = "meter", "kelvin"


def _mesh(nodes_x: int = 5, nodes_y: int = 5, mesh_id: str = "plate") -> StructuredMesh:
    return StructuredMesh(
        mesh_id=mesh_id, length_x=Quantity(0.01, METER), length_y=Quantity(0.01, METER),
        nodes_x=nodes_x, nodes_y=nodes_y,
    )


def _definition(*, unit: str = KELVIN, components: int = 1, mesh_id: str = "plate",
                location: FieldLocation = FieldLocation.NODE) -> FieldDefinition:
    return FieldDefinition(field_id="T", unit=unit, mesh_id=mesh_id, location=location,
                           components=components)


def _contract(**overrides) -> FieldTransferContract:
    mesh = _mesh()
    fields = dict(
        producer=_definition(), producer_fingerprint=mesh.fingerprint(),
        consumer=_definition(), consumer_fingerprint=mesh.fingerprint(),
        kind=TransferKind.FIELD_TRANSFER, verdict=FieldTransferVerdict.COMPATIBLE,
        reason="one support, one unit, one location",
    )
    fields.update(overrides)
    return FieldTransferContract(**fields)


def _values(m: StructuredMesh, *, left: float = 400.0, right: float = 300.0) -> np.ndarray:
    """A field that differs between the two edges, so which edge was read is visible."""
    xs, ys = m.axis_coordinates()
    out = np.empty(m.node_count, dtype=np.float64)
    span = max(xs[-1] - xs[0], 1e-30)
    for i, x in enumerate(xs):
        for j, _y in enumerate(ys):
            out[m.node_index(i, j)] = left + (right - left) * (x - xs[0]) / span
    return out


def _region_operator(**overrides) -> FieldObservationOperator:
    mesh = _mesh()
    fields = dict(
        operator_id="edge.mean", kind=FieldObservationKind.REGION_MEAN, field_id="T",
        mesh_fingerprint=mesh.fingerprint(), unit=KELVIN, region_id="edge",
    )
    fields.update(overrides)
    return FieldObservationOperator(**fields)


def _probe(**overrides) -> FieldObservationOperator:
    mesh = _mesh()
    fields = dict(
        operator_id="probe", kind=FieldObservationKind.PROBE_AT_LOCATION, field_id="T",
        mesh_fingerprint=mesh.fingerprint(), unit=KELVIN,
        probe_x=Quantity(0.005, METER), probe_y=Quantity(0.005, METER),
    )
    fields.update(overrides)
    return FieldObservationOperator(**fields)


# ---------------------------------------------------------------------------
# a_contract_may_not_claim_more_than_its_own_records_allow
# ---------------------------------------------------------------------------
def test_r63_an_honest_contract_is_unchanged():
    """The control: what check_field_transfer itself produces still constructs."""
    mesh = _mesh()
    contract = check_field_transfer(_definition(), mesh, _definition(), mesh)
    assert contract.verdict is FieldTransferVerdict.COMPATIBLE
    assert contract.may_cross_directly is True


@pytest.mark.xfail(strict=True, reason="R-63 finding 77 as audited: a payload computed as REFUSED for 1 component against 3 reads back as COMPATIBLE, with may_cross_directly True")
def test_r63_a_component_mismatch_cannot_read_back_as_compatible():
    mesh = _mesh()
    refused = check_field_transfer(_definition(), mesh, _definition(components=3), mesh)
    assert refused.verdict is FieldTransferVerdict.REFUSED, refused.reason
    forged = dict(refused.to_dict())
    forged["verdict"] = FieldTransferVerdict.COMPATIBLE.value
    with pytest.raises(InvalidScientificProblem, match="component|verdict"):
        FieldTransferContract.from_dict(forged)


@pytest.mark.xfail(strict=True, reason="R-63 as audited: kelvin against pascal does the same, and no projection repairs a dimension")
def test_r63_a_dimension_mismatch_cannot_read_back_as_compatible():
    with pytest.raises(InvalidScientificProblem, match="dimension|verdict"):
        _contract(consumer=_definition(unit="pascal"))


@pytest.mark.xfail(strict=True, reason="R-63 as audited: direct construction with made-up fingerprints claims COMPATIBLE for two supports that are not the same one")
def test_r63_two_different_supports_cannot_read_back_as_compatible():
    with pytest.raises(InvalidScientificProblem, match="fingerprint|support|verdict"):
        _contract(consumer_fingerprint="a" * 64)


@pytest.mark.xfail(strict=True, reason="R-63: two locations on one geometry need a declared projection, and the verdict was never checked against the definitions that say so")
def test_r63_two_locations_cannot_read_back_as_compatible():
    with pytest.raises(InvalidScientificProblem, match="location|verdict"):
        _contract(consumer=_definition(location=FieldLocation.CELL))


@pytest.mark.xfail(strict=True, reason="R-63: and two units of one dimension need a conversion, which COMPATIBLE says is not needed")
def test_r63_two_units_cannot_read_back_as_compatible():
    with pytest.raises(InvalidScientificProblem, match="unit|verdict"):
        _contract(consumer=_definition(unit="degC"))


def test_r63_a_more_conservative_verdict_is_still_allowed():
    """The control: a caller may refuse for a reason the record does not carry."""
    assert _contract(verdict=FieldTransferVerdict.REFUSED,
                     reason="the producing run was not trusted").verdict is (
        FieldTransferVerdict.REFUSED)


# ---------------------------------------------------------------------------
# a_region_mean_names_the_region_it_reads_by_content
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-73 finding 104 as audited: apply() checks region.region_id only, so the same operator and digest read the left edge or the right edge depending on which region object is supplied")
def test_r73_a_region_mean_refuses_a_region_whose_content_is_not_the_declared_one():
    mesh = _mesh()
    values = _values(mesh)
    names = {field.name for field in dataclasses.fields(FieldObservationOperator)}
    assert {"region_edge", "region_mesh_id"} <= names, (
        "the operator has nowhere to say which region content it reads, so any region with a matching id "
        "is applied")
    left = MeshRegion(region_id="edge", mesh_id="plate", edge=BoundaryEdge.LEFT)
    right = MeshRegion(region_id="edge", mesh_id="plate", edge=BoundaryEdge.RIGHT)
    operator = _region_operator(region_edge=BoundaryEdge.LEFT.value, region_mesh_id="plate")
    assert operator.apply(mesh, values, region=left).magnitude_in(KELVIN) == pytest.approx(400.0)
    with pytest.raises(FieldObservationError, match="edge|region"):
        operator.apply(mesh, values, region=right)


@pytest.mark.xfail(strict=True, reason="R-73: and the region's content is not in the operator's digest, so two observations of different edges are one observation")
def test_r73_the_region_content_is_part_of_the_operators_identity():
    names = {field.name for field in dataclasses.fields(FieldObservationOperator)}
    assert {"region_edge", "region_mesh_id"} <= names, (
        "the operator cannot say which region content it reads, so its digest cannot cover it")
    left = _region_operator(region_edge=BoundaryEdge.LEFT.value, region_mesh_id="plate")
    right = _region_operator(region_edge=BoundaryEdge.RIGHT.value, region_mesh_id="plate")
    assert left.digest != right.digest


# ---------------------------------------------------------------------------
# a_probe_outside_the_support_is_refused_rather_than_snapped
# ---------------------------------------------------------------------------
def test_r73_a_probe_on_its_support_still_reads_the_nearest_node():
    """The control: snapping inside the support is reported, not refused."""
    mesh = _mesh()
    values = _values(mesh)
    probe = _probe()
    assert probe.apply(mesh, values).magnitude_in(KELVIN) == pytest.approx(350.0)
    assert probe.probe_offset(mesh).magnitude_in(METER) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.xfail(strict=True, reason="R-73 finding 104 as audited: a probe declared 2 m and -5 m away from a 10 mm plate silently returns a corner node's value, and probe_offset reports 5.38 m only if somebody asks")
def test_r73_a_probe_outside_the_support_is_refused():
    mesh = _mesh()
    values = _values(mesh)
    away = _probe(probe_x=Quantity(2.0, METER), probe_y=Quantity(-5.0, METER))
    assert away.probe_offset(mesh).magnitude_in(METER) > 1.0, "the offset was always computable"
    with pytest.raises(FieldObservationError, match="outside|support"):
        away.apply(mesh, values)


@pytest.mark.xfail(strict=True, reason="R-73: resolve_indices is where the snap happens, and it answered with a corner node for a location that is not on the support at all")
def test_r73_resolving_indices_outside_the_support_is_refused():
    mesh = _mesh()
    away = _probe(probe_x=Quantity(2.0, METER), probe_y=Quantity(-5.0, METER))
    with pytest.raises(FieldObservationError, match="outside|support"):
        away.resolve_indices(mesh)


# ---------------------------------------------------------------------------
# the_values_an_operator_reads_are_the_field_it_names
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-73 as audited: the field values are a bare float array whose unit and field_id are asserted by the operator and never checked")
def test_r73_a_typed_field_of_another_quantity_is_refused():
    from engcore.data.field import FieldValue

    mesh = _mesh()
    velocity = FieldValue(
        definition=FieldDefinition(field_id="u", unit="meter / second", mesh_id="plate",
                                   location=FieldLocation.NODE, components=1),
        mesh=mesh, values=_values(mesh).reshape(mesh.nodes_x, mesh.nodes_y),
    )
    probe = _probe()
    try:
        reading = probe.apply(mesh, velocity)
    except FieldObservationError:
        return
    except TypeError as exc:
        reading = None
        assert reading is not None, (
            f"apply cannot be handed the typed field at all, so the unit and field id on the operator "
            f"stay assertions about an array nobody checked: {exc}")
    assert reading is None, (
        f"a velocity field was read through a temperature operator and came back as {reading}")


@pytest.mark.xfail(strict=True, reason="R-73: and the typed field of the quantity it DOES name is the case that has to keep working")
def test_r73_a_typed_field_of_the_named_quantity_is_read():
    from engcore.data.field import FieldValue

    mesh = _mesh()
    temperature = FieldValue(definition=_definition(), mesh=mesh,
                             values=_values(mesh).reshape(mesh.nodes_x, mesh.nodes_y))
    probe = _probe()
    try:
        reading = probe.apply(mesh, temperature)
    except TypeError as exc:
        reading = None
        assert reading is not None, f"apply cannot be handed the typed field it names: {exc}"
    assert reading.magnitude_in(KELVIN) == pytest.approx(350.0)
