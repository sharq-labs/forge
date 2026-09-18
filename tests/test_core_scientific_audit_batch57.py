"""Core re-audit 2026-09-16, batch 57: one identity rule, so a digest and a comparison agree.

Problems R-62 (finding 76) and R-74 (finding 105), improvement I-23, under
benchmarks/core_v4_false_confidence/BATCH57_THRESHOLD_PROTOCOL.json.

Two identities computed from raw float64 magnitudes. A mesh fingerprint hashes
`repr(magnitude_in("meter"))`, so 7 mm and 0.7 cm -- the same rectangle, stated twice -- hash
differently, because the conversions land on 0.007 and 0.006999999999999999. A parameter digest hashes
the same kind of number, so a bound restated in millivolts is a different parameter, and `-0.0` is ONE
value to `differences()` and TWO to the digest. Meanwhile the transfer check compares geometry with
`1e-12 * max(1.0, |x|)`, which below one metre is an ABSOLUTE 1e-12 m, so 10 nm and 10.0005 nm are the
same rectangle and a transfer between two different geometries is reported as a resolution difference
a projection can close.

Recorded as strict xfails before the fix, each seen failing on its own assertion.
"""

from __future__ import annotations

import importlib
import json

import pytest

from engcore.inference.parameters import ParameterBounds, ParameterIdentity, ParameterTransform
from engcore.scientific.fields.mesh import StructuredMesh
from engcore.scientific.fields.transfer import (
    FieldDefinition, FieldTransferVerdict, check_field_transfer,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units import Quantity


def _helper():
    """The one canonical-magnitude rule, or a failure naming its absence."""
    module = importlib.import_module("engcore.scientific.units.quantity")
    found = getattr(module, "canonical_magnitude", None)
    assert found is not None, (
        "engcore.scientific.units.quantity has no `canonical_magnitude`: there is no shared rule, so "
        "every identity that hashes a length or a bound rounds float64 noise into its own answer")
    return module, found


def _mesh(length, *, nodes=(5, 5), origin=None, mesh_id="m"):
    origin = origin or (Quantity(0.0, "meter"), Quantity(0.0, "meter"))
    return StructuredMesh(mesh_id=mesh_id, length_x=length, length_y=length,
                          nodes_x=nodes[0], nodes_y=nodes[1],
                          origin_x=origin[0], origin_y=origin[1])


def _parameter(lower, upper, *, unit="volt", name="v"):
    return ParameterIdentity(
        name=name, unit=unit,
        model=ModelReference(model_id="m", version="1"),
        bounds=ParameterBounds(lower=lower, upper=upper),
        transform=ParameterTransform.IDENTITY,
    )


# ---------------------------------------------------------------------------
# R-62: the mesh
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-62 finding 76: a mesh fingerprint hashes raw float64 magnitudes, so 7 mm and 0.7 cm are two supports")
def test_r62_the_same_rectangle_stated_in_two_units_is_one_support():
    """The audited case: 7 mm and 0.7 cm, whose conversions differ in the 16th digit."""
    millimetres, centimetres = Quantity(7.0, "millimeter"), Quantity(0.7, "centimeter")
    assert millimetres.magnitude_in("meter") != centimetres.magnitude_in("meter"), (
        "the two conversions agree exactly, so this case no longer measures anything")
    left, right = _mesh(millimetres), _mesh(centimetres)
    assert left.fingerprint() == right.fingerprint(), (
        "the same rectangle stated in two units is two supports, so a field produced on one cannot "
        "be read on the other")
    assert left.same_support_as(right)


def test_r62_a_rectangle_that_really_differs_is_still_two_supports():
    """The control, and the reason the rule is a RELATIVE one: 10 nm against 10.0005 nm."""
    left, right = _mesh(Quantity(10.0, "nanometer")), _mesh(Quantity(10.0005, "nanometer"))
    assert left.fingerprint() != right.fingerprint()
    assert not left.same_support_as(right)


@pytest.mark.xfail(strict=True, reason="R-62 finding 76: the geometry comparison's 1e-12 floor is absolute below one metre")
def test_r62_the_transfer_check_reads_geometry_the_way_the_fingerprint_does():
    """The absolute 1e-12 m floor: two rectangles 5e-5 apart relatively read as one."""
    producer_mesh = _mesh(Quantity(10.0, "nanometer"), nodes=(5, 5), mesh_id="p")
    consumer_mesh = _mesh(Quantity(10.0005, "nanometer"), nodes=(9, 9), mesh_id="c")
    producer = FieldDefinition(field_id="T", unit="kelvin", mesh_id="p")
    consumer = FieldDefinition(field_id="T", unit="kelvin", mesh_id="c")
    contract = check_field_transfer(producer, producer_mesh, consumer, consumer_mesh)
    assert contract.verdict is FieldTransferVerdict.REFUSED, (
        f"two rectangles that differ by 5e-5 relatively are reported {contract.verdict.value}, so a "
        f"projection is offered for a difference no projection can close")
    assert "different rectangle" in contract.reason, contract.reason


def test_r62_the_same_rectangle_at_two_resolutions_is_still_a_resolution_difference():
    """The control: the verdict a projection CAN close must still be that one."""
    producer = FieldDefinition(field_id="T", unit="kelvin", mesh_id="p")
    consumer = FieldDefinition(field_id="T", unit="kelvin", mesh_id="c")
    contract = check_field_transfer(
        producer, _mesh(Quantity(7.0, "millimeter"), nodes=(5, 5), mesh_id="p"),
        consumer, _mesh(Quantity(0.7, "centimeter"), nodes=(9, 9), mesh_id="c"))
    assert contract.verdict is FieldTransferVerdict.REQUIRES_PROJECTION, (
        f"{contract.verdict.value}: {contract.reason}")
    assert "two resolutions" in contract.reason, contract.reason


# ---------------------------------------------------------------------------
# R-74: the parameter
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-74 finding 105: the same bound in mV and V is a different identity")
def test_r74_a_bound_restated_in_another_unit_is_the_same_parameter():
    """274 of 2000 random millivolt/volt restatements disagreed in the measurement."""
    # -3.7911 V and -3791.1 mV: the conversion lands on -3.7911000000000006, one of 2838 such
    # disagreements in 20000 random four-decimal bounds.
    in_volts = _parameter(Quantity(-3.7911, "volt"), Quantity(2.1119, "volt"))
    in_millivolts = _parameter(Quantity(-3791.1, "millivolt"), Quantity(2111.9, "millivolt"))
    assert in_volts.differences(in_millivolts) == ()
    assert in_volts.digest == in_millivolts.digest, (
        "the same admissible range stated in millivolts is a different parameter identity")


@pytest.mark.xfail(strict=True, reason="R-74 finding 105: -0.0 and 0.0 show no difference and have different digests")
def test_r74_a_negative_zero_bound_is_one_value_in_both_directions():
    """`-0.0 == 0.0` is True and `json.dumps(-0.0)` is `-0.0`: one value, two digests."""
    negative = _parameter(Quantity(-0.0, "volt"), Quantity(1.0, "volt"))
    positive = _parameter(Quantity(0.0, "volt"), Quantity(1.0, "volt"))
    assert negative.differences(positive) == (), "the comparison already calls these one parameter"
    assert negative.digest == positive.digest, (
        "two bounds the comparison calls equal have two digests, so a record keyed by digest holds "
        "the same parameter twice")
    assert json.dumps(-0.0) == "-0.0", "the preimage no longer carries a sign, so this case is moot"


def test_r74_a_bound_that_really_differs_is_still_a_different_parameter():
    """The control: 12 significant digits, not a free pass."""
    left = _parameter(Quantity(0.0, "volt"), Quantity(1.0, "volt"))
    right = _parameter(Quantity(1e-11, "volt"), Quantity(1.0, "volt"))
    assert left.differences(right) == ("lower",)
    assert left.digest != right.digest


# ---------------------------------------------------------------------------
# the shared rule itself
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="I-23: there is no shared rule for how much of a float is identity")
def test_i23_one_rule_states_how_much_of_a_float_is_identity():
    module, canonical = _helper()
    digits = getattr(module, "IDENTITY_SIGNIFICANT_DIGITS", None)
    assert digits == 12, f"the convention is not declared as a number: {digits!r}"
    assert canonical(Quantity(7.0, "millimeter"), "meter") == canonical(
        Quantity(0.7, "centimeter"), "meter")
    assert canonical(Quantity(-0.0, "volt"), "volt") == 0.0
    assert repr(canonical(Quantity(-0.0, "volt"), "volt")) == "0.0", "the sign survives the rule"
    assert canonical(Quantity(10.0, "nanometer"), "meter") != canonical(
        Quantity(10.0005, "nanometer"), "meter")
    # A value that differs in the 13th significant digit is one identity, and that is the decision.
    assert canonical(Quantity(1.0, "meter"), "meter") == canonical(
        Quantity(1.0000000000001, "meter"), "meter")
    assert canonical(Quantity(1.0, "meter"), "meter") != canonical(
        Quantity(1.00000000001, "meter"), "meter")
    with pytest.raises(Exception):
        canonical(Quantity(1.0, "meter"), "kelvin")


@pytest.mark.xfail(strict=True, reason="I-23: each identity rounds float64 noise into its own answer")
def test_i23_the_mesh_and_the_parameter_read_the_same_rule():
    """One rule, two identities: a second copy of it is a second answer waiting to happen."""
    module, _canonical = _helper()
    mesh_source = importlib.import_module("engcore.scientific.fields.mesh")
    parameter_source = importlib.import_module("engcore.inference.parameters")
    transfer_source = importlib.import_module("engcore.scientific.fields.transfer")
    for where in (mesh_source, parameter_source, transfer_source):
        assert getattr(where, "canonical_magnitude", None) is module.canonical_magnitude, (
            f"{where.__name__} does not read the shared rule, so its identity is its own")
