"""Frozen records that are actually frozen (F07).

``@dataclass(frozen=True)`` protects the **attribute**, not the object behind
it, and every record in ``scientific.results`` was mutable through the mapping
it held. The review reproduced three things, and each has a test here:

1. ``provenance.inputs`` and ``result.values`` accepted a subscript assignment
   after construction;
2. that assignment could inject a **bare number** — the exact value the
   constructor refuses on the grounds that it is not a scientific result;
3. a record could be mutated **through its own ``to_dict()`` payload**, via a
   nested alias, with no intent at all: ``to_dict`` built a fresh outer dict and
   handed out the record's own nested objects.

The third is the one that matters most, because a payload is the thing a caller
is *supposed* to edit. The fix runs both ways: internal state is recursively
immutable, and ``to_dict`` returns a recursively detached payload.

This is not tamper-proofing and does not claim to be — ``object.__setattr__``
still reaches everything here, as it does everywhere in this repository. The
guarantee is against accident and ordinary use.
"""

from __future__ import annotations

import copy
import json
import pickle

import pytest

from src.engcore.mcp.evidence import AssertedContext
from src.engcore.scientific.errors import ScientificCoreError
from src.engcore.scientific.results.immutable import (
    FrozenList,
    FrozenMapping,
    FrozenSet,
    detach,
    freeze,
)
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.result import ScientificResult
from src.engcore.scientific.units.quantity import Quantity

K = "kelvin"


def provenance():
    return ProvenanceRecord(
        run_id="immutability",
        software_version="test/1",
        models=(("m.a", "1"),),
        inputs={"heat_capacity": Quantity(2.5, "joule/kelvin")},
        tolerances={"rtol": 1e-9},
        environment={"python": "3.14"},
        metadata={"nested": {"deep": 1}, "tags": ["a", "b"]},
    )


def result(prov=None):
    return ScientificResult(
        result_id="immutability",
        values={"final_temperature": Quantity(338.577018, K)},
        models=(("m.a", "1"),),
        provenance=prov or provenance(),
        metadata={"nested": {"deep": 1}, "tags": ["a", "b"]},
    )


# =====================================================================
# 1 and 2 — the mappings cannot be written to at all
# =====================================================================

def test_provenance_inputs_cannot_be_mutated_after_construction():
    record = provenance()
    with pytest.raises((TypeError, AttributeError)):
        record.inputs["injected"] = Quantity(1.0, K)
    with pytest.raises((TypeError, AttributeError)):
        del record.inputs["heat_capacity"]
    assert set(record.inputs) == {"heat_capacity"}


def test_result_values_cannot_be_mutated_after_construction():
    record = result()
    with pytest.raises((TypeError, AttributeError)):
        record.values["injected"] = Quantity(1.0, K)
    assert set(record.values) == {"final_temperature"}


def test_a_bare_number_cannot_be_injected_after_the_check_that_refuses_it():
    """The constructor's own rule, defeated one line later.

    ``ScientificResult`` refuses a bare number in ``values`` because "a bare
    number is not a scientific result". Writing one in afterwards was accepted,
    and ``to_dict`` then died on it with ``'int' object has no attribute
    'to_dict'`` — the record having become one the constructor would never have
    built.
    """
    with pytest.raises(ScientificCoreError, match="bare number"):
        ScientificResult(
            result_id="r", values={"v": 5}, provenance=provenance()
        )

    record = result()
    with pytest.raises((TypeError, AttributeError)):
        record.values["v"] = 5
    for name, value in record.values.items():
        assert isinstance(value, Quantity), name
    record.to_dict()  # still serializable, because it is still a result


@pytest.mark.parametrize(
    "field", ["inputs", "tolerances", "environment", "metadata"]
)
def test_every_provenance_mapping_is_frozen(field):
    record = provenance()
    with pytest.raises((TypeError, AttributeError)):
        getattr(record, field)["injected"] = 1


@pytest.mark.parametrize("field", ["values", "validity", "uncertainty", "metadata"])
def test_every_result_mapping_is_frozen(field):
    record = result()
    with pytest.raises((TypeError, AttributeError)):
        getattr(record, field)["injected"] = 1


def test_nested_metadata_is_protected_too():
    """Not the outer mapping alone: there is no depth at which it reopens."""
    record = result()
    with pytest.raises((TypeError, AttributeError)):
        record.metadata["nested"]["deep"] = 999
    with pytest.raises((TypeError, AttributeError)):
        record.metadata["tags"].append("c")
    assert record.metadata["nested"]["deep"] == 1
    assert record.provenance.metadata["nested"]["deep"] == 1
    with pytest.raises((TypeError, AttributeError)):
        record.provenance.metadata["nested"]["deep"] = 999


# =====================================================================
# 3 — the payload is a copy, at every depth
# =====================================================================

def test_editing_a_result_payload_does_not_change_the_result():
    record = result()
    payload = record.to_dict()
    payload["metadata"]["nested"]["deep"] = 999
    payload["metadata"]["tags"].append("c")
    assert record.metadata["nested"]["deep"] == 1
    assert list(record.metadata["tags"]) == ["a", "b"]


def test_editing_a_provenance_payload_does_not_change_the_provenance():
    record = provenance()
    payload = record.to_dict()
    payload["metadata"]["nested"]["deep"] = 999
    payload["tolerances"]["forged"] = 1.0
    payload["environment"]["forged"] = "x"
    assert record.metadata["nested"]["deep"] == 1
    assert "forged" not in record.tolerances
    assert "forged" not in record.environment


def test_editing_a_declaration_payload_does_not_change_the_declaration():
    """A caller's claim is carried verbatim, which has to mean a copy."""
    declaration = AssertedContext(
        source="LumpedApplicabilityDeclaration",
        payload={"regime": "forced", "nested": {"deep": 1}},
    )
    payload = declaration.to_dict()
    payload["payload"]["nested"]["deep"] = 999
    assert declaration.payload["nested"]["deep"] == 1


def test_the_payload_is_plain_json_types_at_every_depth():
    """Detached means detached *and* ordinary: a payload is a message."""
    payload = result().to_dict()
    assert json.dumps(payload, sort_keys=True)
    assert type(payload["metadata"]) is dict
    assert type(payload["metadata"]["nested"]) is dict
    assert type(payload["metadata"]["tags"]) is list


def test_a_payload_still_round_trips_to_an_equal_record():
    record = result()
    restored = ScientificResult.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.metadata == record.metadata
    assert restored.provenance.inputs == record.provenance.inputs


# =====================================================================
# The primitives
# =====================================================================

def test_a_frozen_mapping_still_equals_the_dict_it_replaced():
    """Freezing must not be a silent behaviour change."""
    record = result()
    assert record.metadata == {"nested": {"deep": 1}, "tags": ["a", "b"]}
    assert {"nested": {"deep": 1}, "tags": ["a", "b"]} == record.metadata
    assert dict(record.metadata)["nested"] == {"deep": 1}
    assert FrozenList(["a", "b"]) == ["a", "b"]
    assert ["a", "b"] == FrozenList(["a", "b"])
    assert FrozenSet({1, 2}) == {1, 2}


def test_freeze_shares_immutable_leaves_rather_than_copying_them():
    """The cost argument, asserted: reading is free and leaves are not copied."""
    quantity = Quantity(1.0, K)
    frozen = freeze({"q": quantity, "s": "text"})
    assert frozen["q"] is quantity
    assert frozen["s"] is "text" or frozen["s"] == "text"
    # and an already-frozen container is returned as it is
    assert freeze(frozen) is frozen


def test_detach_restores_the_shapes_it_was_given():
    original = {"m": {"a": 1}, "l": [1, 2], "t": (1, 2), "s": {1, 2}}
    round_tripped = detach(freeze(original))
    assert round_tripped == original
    assert type(round_tripped["m"]) is dict
    assert type(round_tripped["l"]) is list
    assert type(round_tripped["t"]) is tuple
    assert type(round_tripped["s"]) is set


def test_frozen_containers_survive_pickle_and_deepcopy():
    """Records are persisted and replayed; the containers must travel."""
    record = result()
    for clone in (pickle.loads(pickle.dumps(record)), copy.deepcopy(record)):
        assert clone.metadata == record.metadata
        assert isinstance(clone.metadata, FrozenMapping)
        with pytest.raises((TypeError, AttributeError)):
            clone.metadata["nested"]["deep"] = 999


def test_dataclasses_replace_still_works_and_refreezes():
    import dataclasses

    record = result()
    replaced = dataclasses.replace(record, result_id="other")
    assert replaced.metadata == record.metadata
    with pytest.raises((TypeError, AttributeError)):
        replaced.metadata["nested"]["deep"] = 999


def test_every_mutating_dict_method_is_refused():
    """The list of overrides is asserted complete, not trusted.

    ``FrozenMapping`` is a ``dict`` subclass, so it inherits the mutators and
    has to override them — and "a list somebody will forget to extend" is the
    real objection to that design. This is that objection answered: the split
    of ``dict``'s own API into mutating and non-mutating is checked against the
    running interpreter, so a future CPython that grows a ``dict`` method fails
    here and gets classified, rather than opening a hole in silence.
    """
    from collections.abc import Mapping

    from src.engcore.scientific.results.immutable import (
        DICT_MUTATORS,
        DICT_NON_MUTATORS,
    )

    dict_only = set(dir(dict)) - set(dir(Mapping))
    assert dict_only == DICT_MUTATORS | DICT_NON_MUTATORS
    assert not (DICT_MUTATORS & DICT_NON_MUTATORS)

    frozen = freeze({"a": 1})
    for name in DICT_MUTATORS:
        assert getattr(type(frozen), name) is not getattr(dict, name), name

    with pytest.raises(TypeError):
        frozen["b"] = 2
    with pytest.raises(TypeError):
        frozen.update({"b": 2})
    with pytest.raises(TypeError):
        frozen.pop("a")
    with pytest.raises(TypeError):
        frozen.popitem()
    with pytest.raises(TypeError):
        frozen.setdefault("b", 2)
    with pytest.raises(TypeError):
        frozen.clear()
    with pytest.raises(TypeError):
        del frozen["a"]
    with pytest.raises(TypeError):
        frozen |= {"b": 2}
    assert dict(frozen) == {"a": 1}


def test_copy_gives_a_mutable_dict_and_the_record_keeps_its_own():
    """The answer to "how do I get one I can edit"."""
    record = result()
    editable = record.metadata.copy()
    assert type(editable) is dict
    editable["nested"] = "replaced"
    assert record.metadata["nested"] == {"deep": 1}


def test_a_frozen_mapping_is_a_dict_where_the_repository_expects_one():
    """Serializable, splattable, and isinstance-checkable.

    Not cosmetic: a study binding is read out of a record's metadata and handed
    straight to ``json.dumps`` in the multirotor pack, and every consumer that
    does ``{**record.metadata}`` or ``isinstance(x, dict)`` relies on this.
    """
    record = result()
    assert isinstance(record.metadata, dict)
    assert json.dumps(record.metadata, sort_keys=True)
    assert {**record.metadata} == dict(record.metadata)
    assert json.dumps(record.provenance.inputs, default=str)
