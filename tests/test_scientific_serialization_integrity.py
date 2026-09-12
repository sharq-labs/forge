"""A malformed wire value must be refused, never quietly reinterpreted.

TWO DEFECTS
-----------
**Boolean scientific fields were coerced.** ``bool("false")`` is ``True``, so a
record written by a producer that lost the type did not arrive corrupted -- it
arrived **inverted**, as a confident statement of the opposite. Five boolean
fields cross the wire in this core and exactly one of them was guarded:

===================================  ==========================================
``RangeCondition.conservative_screen``  guarded (``_strict_bool``)
``FlagCondition.expected``              coerced -- inverts a declaration
``CrossLimitCondition.minimum_inclusive`` coerced -- moves an endpoint
``CrossLimitCondition.maximum_inclusive`` coerced -- moves an endpoint
``ModelInputSpec.required``             coerced -- makes an input optional
``ConstraintCheck.satisfied``           coerced -- **a violated constraint reads
                                        back satisfied**
===================================  ==========================================

The last is the sharpest, because it is a *verdict* rather than a declaration.
The rule was a private helper in the model package; it is a property of reading
a wire format, so it now lives at the serialization boundary and all five use it.

**``to_json`` emitted bare ``NaN`` and ``Infinity``.** Python's ``json`` writes
non-finite floats as tokens that are **not in the JSON grammar**, so the record
serialized without complaint and produced a document Python could read back and
no conforming reader could. That is worse than failing to serialize: the failure
surfaces at the consumer, long after the run that could have explained it.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.errors import (
    InvalidScientificProblem,
    ModelValidityError,
    ScientificCoreError,
)
from engcore.scientific.ir.constraints import ConstraintCheck
from engcore.scientific.models.definition import (
    CrossLimitCondition,
    FlagCondition,
    InputSourceKind,
    ModelInputSpec,
    RangeCondition,
)
from engcore.scientific.serialization import require_bool, to_json
from engcore.scientific.units.quantity import Quantity

#: Everything a producer emits when it loses the type of a boolean. Each is
#: refused, and `"false"`/`0` are the ones that would INVERT rather than merely
#: corrupt.
NOT_BOOLEANS = ["false", "true", "False", "True", "", "no", 0, 1, 0.0, 1.0, None, []]


# ============================================================ boolean fields


def _round_trip(record):
    return type(record).from_dict(record.to_dict())


@pytest.mark.parametrize("bad", NOT_BOOLEANS)
def test_a_flag_conditions_expectation_cannot_arrive_as_a_non_boolean(bad):
    """The inversion, on a condition that decides whether a model applies.

    `FlagCondition(expected=False)` means "this model requires the flag to be
    OFF". Written as the string "false" by a lossy producer and coerced back,
    it becomes "requires the flag to be ON" -- and every case the condition was
    written to catch now passes.
    """
    payload = FlagCondition(name="steady_state", expected=False).to_dict()
    payload["expected"] = bad
    with pytest.raises(ModelValidityError):
        FlagCondition.from_dict(payload)


@pytest.mark.parametrize("bad", NOT_BOOLEANS)
@pytest.mark.parametrize("key", ["minimum_inclusive", "maximum_inclusive"])
def test_a_cross_limit_endpoint_cannot_arrive_as_a_non_boolean(key, bad):
    """An endpoint flag decides whether a value exactly on the bound passes."""
    condition = CrossLimitCondition(
        name="ratio",
        numerator="operating_temperature",
        denominator="maximum_operating_temperature",
        maximum=Quantity(1.0, "dimensionless"),
    )
    payload = condition.to_dict()
    payload[key] = bad
    with pytest.raises(ModelValidityError):
        CrossLimitCondition.from_dict(payload)


@pytest.mark.parametrize("bad", NOT_BOOLEANS)
def test_a_model_input_requirement_cannot_arrive_as_a_non_boolean(bad):
    """`required` decides whether an absent input is a gap or a non-event."""
    spec = ModelInputSpec(
        name="ambient_temperature",
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar="kelvin",
    )
    payload = spec.to_dict()
    payload["required"] = bad
    with pytest.raises(ModelValidityError):
        ModelInputSpec.from_dict(payload)


@pytest.mark.parametrize("bad", NOT_BOOLEANS)
def test_a_constraint_verdict_cannot_arrive_as_a_non_boolean(bad):
    """The sharpest one: a VERDICT, not a declaration.

    A violated constraint written as `"false"` and coerced back reads
    `satisfied=True` -- a design that broke its limit reported as one that met
    it, on the record a reader consults to find out.
    """
    check = ConstraintCheck(
        constraint="peak_temperature",
        satisfied=False,
        margin=Quantity(-12.0, "kelvin"),
        value=Quantity(412.0, "kelvin"),
    )
    payload = check.to_dict()
    payload["satisfied"] = bad
    with pytest.raises(InvalidScientificProblem):
        ConstraintCheck.from_dict(payload)


def test_the_screen_flag_that_was_already_guarded_still_is():
    """The one field that had the rule, kept exercised beside the four that did not."""
    payload = RangeCondition(
        name="internal_fourier_number",
        minimum=Quantity(0.2, "dimensionless"),
        conservative_screen=True,
    ).to_dict()
    payload["conservative_screen"] = "false"
    with pytest.raises(ModelValidityError):
        RangeCondition.from_dict(payload)


@pytest.mark.parametrize(
    "record",
    [
        FlagCondition(name="steady_state", expected=False),
        FlagCondition(name="linear", expected=True),
        CrossLimitCondition(
            name="ratio",
            numerator="operating_temperature",
            denominator="maximum_operating_temperature",
            maximum=Quantity(1.0, "dimensionless"),
            minimum_inclusive=False,
            maximum_inclusive=True,
        ),
        ModelInputSpec(
            name="ambient_temperature",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar="kelvin",
            required=False,
        ),
        ConstraintCheck(
            constraint="peak_temperature",
            satisfied=False,
            margin=Quantity(-12.0, "kelvin"),
            value=Quantity(412.0, "kelvin"),
        ),
        ConstraintCheck(
            constraint="peak_temperature",
            satisfied=True,
            margin=Quantity(12.0, "kelvin"),
            value=Quantity(388.0, "kelvin"),
        ),
    ],
)
def test_a_well_formed_boolean_still_round_trips_to_the_same_value(record):
    """Both truth values, on every guarded field.

    A rule that refused everything would pass every test above and break the
    platform. `False` specifically: it is the value a truthiness bug destroys,
    so a round trip that only ever carried `True` would prove nothing.
    """
    assert _round_trip(record) == record


def test_an_absent_boolean_is_still_the_additive_default():
    """A record written before the field existed must still load.

    This is the compatibility half of the rule and it is deliberate: absence
    had exactly one meaning while the field did not exist, so it can be
    defaulted. A key that is PRESENT and malformed cannot.
    """
    payload = FlagCondition(name="steady_state", expected=True).to_dict()
    del payload["expected"]
    assert FlagCondition.from_dict(payload).expected is True

    payload = ModelInputSpec(
        name="t", source_kind=InputSourceKind.PARAMETER, unit_exemplar="kelvin"
    ).to_dict()
    del payload["required"]
    assert ModelInputSpec.from_dict(payload).required is True

    payload = RangeCondition(
        name="r", minimum=Quantity(1.0, "dimensionless")
    ).to_dict()
    del payload["conservative_screen"]
    assert RangeCondition.from_dict(payload).conservative_screen is False


def test_the_helper_states_the_zero_and_one_decision_rather_than_inheriting_it():
    """`0` and `1` are refused, and that is a decision.

    They are what a writer produces by losing the type. Accepting them would
    make "this writer lost the type" indistinguishable from "this writer meant
    False", so a record from a broken producer would read as a confident
    scientific statement.
    """
    assert require_bool({"k": True}, "k", False) is True
    assert require_bool({"k": False}, "k", True) is False
    assert require_bool({}, "k", True) is True
    assert require_bool({}, "k", False) is False

    for bad in (0, 1, "false", "true"):
        with pytest.raises(ScientificCoreError):
            require_bool({"k": bad}, "k", False)

    # The caller's own error type is used, so a refusal arrives in the category
    # that caller already documents.
    with pytest.raises(ModelValidityError):
        require_bool({"k": "false"}, "k", False, error=ModelValidityError)


def test_the_truthiness_facts_behind_this_whole_module():
    """Asserted, so the reasoning is falsifiable rather than claimed."""
    assert bool("false") is True
    assert bool("False") is True
    assert bool(0) is False and bool(1) is True
    assert isinstance(True, int), "bool is an int subclass; 0/1 need refusing explicitly"
    assert not isinstance(1, bool)


# ================================================================ JSON output


class _Record:
    """Minimal record with a `to_dict`, so this tests `to_json` and not a type."""

    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")]
)
def test_a_non_finite_float_cannot_be_written_down(value):
    """`NaN` and `Infinity` are not JSON. A record carrying one is refused here."""
    with pytest.raises(ScientificCoreError):
        to_json(_Record({"schema": "probe/1", "residual": value}))


def test_the_refusal_reaches_arbitrarily_deep_into_a_payload():
    """Nested, because that is where a stray non-finite actually hides."""
    with pytest.raises(ScientificCoreError):
        to_json(
            _Record(
                {
                    "schema": "probe/1",
                    "checks": [{"name": "a", "residual": 1.0},
                               {"name": "b", "residual": float("nan")}],
                }
            )
        )
    with pytest.raises(ScientificCoreError):
        to_json(
            _Record({"schema": "probe/1", "a": {"b": {"c": float("inf")}}})
        )


def test_what_the_old_behaviour_actually_produced():
    """The defect, demonstrated rather than described.

    `json.dumps` with its default `allow_nan=True` emits bare `NaN`, which
    `json.loads` accepts because Python extends the grammar -- and which a
    conforming reader rejects. That asymmetry is the whole reason this looked
    fine for as long as it did: every check anybody ran was in Python.
    """
    permissive = json.dumps({"residual": float("nan")})
    assert "NaN" in permissive
    assert json.loads(permissive)["residual"] != json.loads(permissive)["residual"]
    with pytest.raises(ValueError):
        json.dumps({"residual": float("nan")}, allow_nan=False)


def test_finite_records_still_serialize_deterministically():
    """The fix must not have changed what a valid record looks like."""
    payload = {"schema": "probe/1", "b": 2.0, "a": {"z": 1, "y": [3, 4]}}
    once = to_json(_Record(payload))
    twice = to_json(_Record(json.loads(once)))
    assert once == twice
    assert once == '{"a": {"y": [3, 4], "z": 1}, "b": 2.0, "schema": "probe/1"}'
    assert json.loads(once) == payload


def test_key_order_does_not_depend_on_insertion_order():
    """Byte-identical output for equal content, which is what pinning rests on."""
    first = to_json(_Record({"schema": "p/1", "a": 1, "b": 2, "c": 3}))
    second = to_json(_Record({"schema": "p/1", "c": 3, "b": 2, "a": 1}))
    assert first == second
