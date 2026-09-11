"""The round's invariants, asserted systematically rather than by example.

WHY THIS MODULE EXISTS BESIDE THE PER-DEFECT ONES
--------------------------------------------------
Each phase's module reproduces its own defect and closes it. That is the right
shape for a fix and the wrong shape for an *invariant*: a check written from a
reproduction covers the case somebody happened to find, and the original defects
in this round survived precisely because the neighbouring case had never been
tried. ``_compare`` was tested with two finite routes and never with three;
``ValidityAssessment`` was cross-checked for IN_DOMAIN-over-violated and never
for the other eight contradictions.

So these enumerate. Where the input space is small enough to exhaust -- three
statuses against eight emptiness patterns, six non-finite pairings across two
and three routes, every mutating method on every frozen container -- it is
exhausted, and the count is asserted so a walk that silently stopped covering
the space fails rather than passing over nothing.

ON HYPOTHESIS
-------------
Not installed in this environment, and not added for this. For the domains
below it would be strictly weaker: these spaces are small and *structured*, and
random sampling from them would cover less than the enumeration does while
taking longer and failing intermittently. Where a space is genuinely large --
float magnitudes in a tolerance comparison -- the interesting values are the
boundary ones, and those are named directly.
"""

from __future__ import annotations

import itertools
import json
import math

import pytest

from engcore.scientific.consensus import (
    ComponentKind,
    CrossSolverConsensus,
    SharedComponent,
    SolveRoute,
)
from engcore.scientific.errors import (
    ModelValidityError,
    ScientificCoreError,
)
from engcore.scientific.ir.conditions import BoundaryCondition, BoundaryKind
from engcore.scientific.models.definition import (
    RangeCondition,
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
    classify_conditions,
)
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.thresholds import VerificationThresholds
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.serialization import to_json
from engcore.scientific.solvers.admission import require_agreement
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity

NON_FINITE = (float("nan"), float("inf"), float("-inf"))
FINITE = (0.0, 1.0, -1.0, 1e-30, 1e30, 350.0)

THRESHOLDS = VerificationThresholds(
    gate_id="invariants", version="1", values={"rel_tol": 1e-9}, basis="fixture"
)


def _route(route_id: str) -> SolveRoute:
    return SolveRoute(
        route_id=route_id,
        solver=SolverIdentity(f"solver.{route_id}", "1"),
        components=frozenset(
            {SharedComponent(kind=ComponentKind.IMPLEMENTATION, name=f"impl-{route_id}")}
        ),
    )


def _consensus(values, required):
    return CrossSolverConsensus.over(
        consensus_id="invariants",
        routes=tuple(_route(name) for name in sorted(values)),
        values=values,
        thresholds=THRESHOLDS,
        tolerance_key="rel_tol",
        required_outputs=required,
    )


# ============ 1. non-finite values never create agreement ==================


def test_no_arrangement_of_non_finite_values_ever_agrees():
    """Every placement of a non-finite reading, over two and three routes.

    The original defect was invisible because `nan > worst` is False, so the
    reading was SKIPPED rather than compared. That failure mode does not depend
    on which route, which quantity, or how many routes -- so none of those is
    fixed here.
    """
    checked = 0
    for route_count in (2, 3):
        route_ids = [chr(ord("A") + i) for i in range(route_count)]
        for bad in NON_FINITE:
            for good in (0.0, 350.0):
                for position in range(route_count):
                    values = {
                        route_id: {"x": good, "y": 1.0}
                        for route_id in route_ids
                    }
                    values[route_ids[position]]["x"] = bad
                    consensus = _consensus(values, ("x", "y"))
                    checked += 1
                    assert consensus.comparison.agreed is False
                    assert consensus.comparison.worst_relative_difference is None
                    assert consensus.establishes is None
    # 3 non-finite values x 2 finite backgrounds x (2 + 3) placements.
    assert checked == 3 * 2 * (2 + 3) == 30, checked


def test_finite_values_that_match_always_agree():
    """The complement, over the same shape.

    Without this the sweep above would pass over a comparison that had stopped
    agreeing with anything at all.
    """
    for route_count in (2, 3):
        for magnitude in FINITE:
            values = {
                chr(ord("A") + i): {"x": magnitude}
                for i in range(route_count)
            }
            consensus = _consensus(values, ("x",))
            assert consensus.comparison.agreed is True
            assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


# ============ 2. invalid tolerances never create agreement =================


def test_no_malformed_tolerance_admits_a_disagreement():
    """Every combination of a bad bound with any other bound.

    Both tolerances are swept together rather than one at a time, because
    `atol + rtol * abs(expected)` is a single expression and a check that only
    ever saw one bad operand could be satisfied by whichever one it read first.
    """
    bad = (*NON_FINITE, -1.0, -1e-30)
    good = (0.0, 1e-9, 1.0)
    checked = 0
    for atol, rtol in itertools.product(bad + good, repeat=2):
        if atol in good and rtol in good:
            continue
        checked += 1
        with pytest.raises(ScientificCoreError):
            require_agreement(
                actual=1.0, expected=1000.0, atol=atol, rtol=rtol,
                error=ScientificCoreError, detail="a real disagreement",
            )
        # ...and it is refused even when the operands agree exactly, so the
        # refusal is about the bound rather than about the numbers.
        with pytest.raises(ScientificCoreError):
            require_agreement(
                actual=1.0, expected=1.0, atol=atol, rtol=rtol,
                error=ScientificCoreError, detail="operands that agree",
            )
    assert checked == 8 * 8 - 3 * 3, checked


# ============ 3. immutable trust records resist alias mutation =============


MUTABLE_RECORDS = [
    (
        "VerificationThresholds.values",
        lambda: VerificationThresholds(
            gate_id="g", version="1", values={"rel_tol": 1e-9}, basis="b"
        ).values,
        "rel_tol",
        1e9,
    ),
    (
        "BoundaryCondition.coefficients",
        lambda: BoundaryCondition(
            name="w", variable="T", kind=BoundaryKind.ROBIN, region="r",
            coefficients={"h": Quantity(5.0, "W/m^2/K")},
        ).coefficients,
        "h",
        Quantity(9999.0, "W/m^2/K"),
    ),
    (
        "ProvenanceRecord.inputs",
        lambda: ProvenanceRecord(
            run_id="r", inputs={"mass": Quantity(2.0, "kg")}
        ).inputs,
        "mass",
        Quantity(9999.0, "kg"),
    ),
    (
        "ProvenanceRecord.metadata",
        lambda: ProvenanceRecord(run_id="r", metadata={"note": "a"}).metadata,
        "note",
        "tampered",
    ),
    (
        "ScientificResult.values",
        lambda: ScientificResult(
            result_id="r",
            values={"T": Quantity(350.0, "kelvin")},
            provenance=ProvenanceRecord(run_id="r"),
        ).values,
        "T",
        Quantity(1.0, "kelvin"),
    ),
]


@pytest.mark.parametrize(
    "label,build,key,replacement",
    MUTABLE_RECORDS,
    ids=[record[0] for record in MUTABLE_RECORDS],
)
def test_every_mutating_method_is_refused_on_a_trust_record(
    label, build, key, replacement
):
    """Not just `__setitem__`. Every name `dict` has that writes.

    A container that refused subscript assignment and accepted `update` would
    have the whole defect back through a different name, and a test that only
    tried the obvious one would not notice.
    """
    container = build()
    before = dict(container)

    with pytest.raises(TypeError):
        container[key] = replacement
    with pytest.raises(TypeError):
        container.update({key: replacement})
    with pytest.raises(TypeError):
        container.pop(key)
    with pytest.raises(TypeError):
        container.popitem()
    with pytest.raises(TypeError):
        container.clear()
    with pytest.raises(TypeError):
        container.setdefault("smuggled", replacement)
    with pytest.raises(TypeError):
        del container[key]
    with pytest.raises(TypeError):
        container |= {key: replacement}

    assert dict(container) == before


def test_the_mutator_list_is_complete_against_this_interpreter():
    """The list above is a list somebody will forget to extend.

    Asserted against the running interpreter rather than trusted, so a future
    CPython that grows a `dict` method fails here and somebody classifies it,
    instead of a new hole opening in silence.
    """
    from engcore.scientific.results.immutable import (
        DICT_MUTATORS,
        DICT_NON_MUTATORS,
    )

    dict_only = set(dir(dict)) - set(dir(object))
    unclassified = dict_only - DICT_MUTATORS - DICT_NON_MUTATORS - {
        "get", "items", "keys", "values", "__class_getitem__",
        "__contains__", "__getitem__", "__iter__", "__len__",
        "__reversed__", "__sizeof__",
    }
    assert unclassified == set(), (
        f"dict has method(s) {sorted(unclassified)} that are classified as "
        f"neither mutating nor non-mutating"
    )


# ============ 4. contradictory validity records cannot exist ===============


def test_exactly_the_derivable_status_is_permitted_for_every_condition_shape():
    """Three statuses against all eight emptiness patterns. Exhaustive.

    For each of the eight shapes exactly ONE status is coherent -- the one
    `classify_conditions` derives -- and the other two must be refused. Testing
    only that "some contradiction raises" would pass over a rule that had gone
    permissive in one branch.
    """
    permitted = 0
    refused = 0
    for has_satisfied, has_violated, has_unknown in itertools.product(
        (False, True), repeat=3
    ):
        satisfied = ("s",) if has_satisfied else ()
        violated = ("v",) if has_violated else ()
        unknown = ("u",) if has_unknown else ()
        reasons = (
            (UnknownCondition(name="u", reason=UnknownReason.NOT_SUPPLIED),)
            if has_unknown
            else ()
        )
        implied = classify_conditions(
            satisfied=satisfied, violated=violated, unknown=unknown
        )
        for status in ValidityStatus:
            fields = dict(
                satisfied=satisfied,
                violated=violated,
                unknown=unknown,
                unknown_reasons=reasons,
            )
            if status is implied:
                assessment = ValidityAssessment(status=status, **fields)
                assert assessment.implied_status is status
                permitted += 1
            else:
                with pytest.raises(ModelValidityError):
                    ValidityAssessment(status=status, **fields)
                refused += 1

    assert permitted == 8, permitted
    assert refused == 16, refused


def test_the_all_empty_shape_is_unknown_and_not_in_domain():
    """The quiet contradiction, named separately because it is the dangerous one.

    Absence of declared limits is not evidence of unlimited validity. An
    assessment that evaluated nothing has established nothing, and IN_DOMAIN
    over three empty lists is the strongest claim in the vocabulary awarded for
    the least work.
    """
    assert ValidityAssessment(status=ValidityStatus.UNKNOWN).status \
        is ValidityStatus.UNKNOWN
    with pytest.raises(ModelValidityError):
        ValidityAssessment(status=ValidityStatus.IN_DOMAIN)
    with pytest.raises(ModelValidityError):
        ValidityAssessment(status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN)


# ============ 9. dependency order does not affect the assessment ===========


def _domain(order):
    """One domain, its conditions declared in the given order.

    `outer` depends on `inner`, so the DECLARATION order and the EVALUATION
    order genuinely differ for at least one permutation.
    """
    conditions = {
        "inner": RangeCondition(
            name="inner", maximum=Quantity(1.0, "dimensionless")
        ),
        "outer": RangeCondition(
            name="outer",
            maximum=Quantity(1.0, "dimensionless"),
            requires=("inner",),
        ),
        "loose": RangeCondition(
            name="loose", maximum=Quantity(1.0, "dimensionless")
        ),
    }
    return ValidityDomain(conditions=tuple(conditions[name] for name in order))


@pytest.mark.parametrize(
    "context",
    [
        {"inner": 0.5, "outer": 0.5, "loose": 0.5},
        {"inner": 5.0, "outer": 0.5, "loose": 0.5},
        {"inner": 0.5, "outer": 5.0, "loose": 0.5},
        {"inner": 0.5, "outer": 0.5, "loose": 5.0},
        {"outer": 0.5, "loose": 0.5},
        {"inner": 0.5},
        {},
    ],
)
def test_declaration_order_never_changes_an_assessment(context):
    """Every permutation of the same conditions must assess identically.

    Evaluation is in dependency order and reporting is in declaration order.
    Those are separated deliberately -- a dependent has to be decided after
    what it depends on, and a reader has to see the domain's own list order --
    and this is what makes the separation checkable: reordering the tuple may
    change the ORDER of the reported names and must never change the VERDICT.
    """
    supplied = {
        name: Quantity(value, "dimensionless") for name, value in context.items()
    }

    verdicts = set()
    for order in itertools.permutations(("inner", "outer", "loose")):
        assessment = _domain(order).assess(supplied)
        verdicts.add(
            (
                assessment.status,
                frozenset(assessment.satisfied),
                frozenset(assessment.violated),
                frozenset(assessment.unknown),
                frozenset(
                    (entry.name, entry.reason)
                    for entry in assessment.unknown_reasons
                ),
            )
        )
    assert len(verdicts) == 1, (
        f"six declaration orders produced {len(verdicts)} different "
        f"assessments of the same context: {verdicts}"
    )


def test_the_reported_order_does_follow_the_declaration():
    """The other half, so the invariant above is not passing over a sort.

    If the reported names were sorted, order-independence would be trivially
    true and the separation it is testing would not exist.
    """
    supplied = {
        name: Quantity(0.5, "dimensionless")
        for name in ("inner", "outer", "loose")
    }
    assert _domain(("loose", "inner", "outer")).assess(supplied).satisfied == (
        "loose", "inner", "outer",
    )
    assert _domain(("outer", "loose", "inner")).assess(supplied).satisfied == (
        "outer", "loose", "inner",
    )


# ============ 8. serialization round trips preserve meaning ================


def _records():
    provenance = ProvenanceRecord(
        run_id="r",
        inputs={"mass": Quantity(2.0, "kilogram")},
        metadata={"nested": {"a": [1, 2, {"b": True}]}},
    )
    return [
        provenance,
        VerificationThresholds(
            gate_id="g", version="1", values={"b": 2.0, "a": 1.0}, basis="b"
        ),
        BoundaryCondition(
            name="w", variable="T", kind=BoundaryKind.ROBIN, region="r",
            coefficients={"h": Quantity(5.0, "W/m^2/K")},
        ),
        ValidityAssessment(
            status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("v",)
        ),
        ScientificResult(
            result_id="r",
            values={"T": Quantity(350.0, "kelvin")},
            provenance=provenance,
        ),
        _consensus({"A": {"x": 1.0}, "B": {"x": 1.0}}, ("x",)),
    ]


@pytest.mark.parametrize(
    "record", _records(), ids=lambda r: type(r).__name__
)
def test_a_record_round_trips_to_an_equal_record_and_identical_bytes(record):
    """Equality AND bytes. Either alone leaves a hole.

    Equal-but-different-bytes means the record is not deterministically
    serializable and cannot be pinned; identical-bytes-but-unequal would mean
    `__eq__` is reading something the payload does not carry.
    """
    once = to_json(record)
    restored = type(record).from_dict(json.loads(once))
    assert restored == record
    assert to_json(restored) == once


@pytest.mark.parametrize(
    "record", _records(), ids=lambda r: type(r).__name__
)
def test_no_record_serializes_a_token_json_cannot_express(record):
    """`NaN` and `Infinity` are not JSON, whatever Python's encoder will emit."""
    text = to_json(record)
    assert "NaN" not in text
    assert "Infinity" not in text
    reparsed = json.loads(text)
    assert isinstance(reparsed, dict)


@pytest.mark.parametrize(
    "record", _records(), ids=lambda r: type(r).__name__
)
def test_a_payload_is_the_callers_and_editing_it_cannot_reach_the_record(record):
    """Detachment, over every record rather than the one that was reported.

    The original defect was `to_dict` handing out the record's own nested
    objects, so a caller who serialized and then edited the payload -- the
    ordinary thing to do with a payload -- silently rewrote the record.
    """
    payload = record.to_dict()
    snapshot = json.dumps(record.to_dict(), sort_keys=True)

    def vandalise(node):
        if isinstance(node, dict):
            for key in list(node):
                node[key] = vandalise(node[key])
            node["__injected__"] = "tampered"
            return node
        if isinstance(node, list):
            return [vandalise(item) for item in node] + ["tampered"]
        return node

    vandalise(payload)
    assert json.dumps(record.to_dict(), sort_keys=True) == snapshot


# ============ the arithmetic every guard above rests on ====================


def test_the_interpreter_still_behaves_the_way_these_guards_assume():
    """Falsifiable rather than asserted in a comment.

    If any of these stopped being true, the guards would keep passing while
    protecting against nothing at all.
    """
    nan = float("nan")
    assert not (nan > 0.0) and not (nan < 0.0) and not (nan == nan)
    assert math.isnan(abs(float("inf") - float("inf")))
    assert math.isnan(float("inf") / float("inf"))
    assert not (999.0 > nan)
    assert bool("false") is True
    assert isinstance(True, int) and not isinstance(1, bool)
