"""CORE-1: the ScientificClaim record -- strict, immutable, serializable, identity-bearing."""

from __future__ import annotations

import copy
import json

import pytest

from claims_support import UNKNOWN_DISCREPANCY, assumption, band_claim, claim, payload
from engcore.claims import (
    ClaimContractError,
    ClaimKind,
    ClaimTarget,
    DecisionBinding,
    EvidenceRequirement,
    QuantityOfInterest,
    RequestedOutput,
    ScientificClaim,
    UncertaintyDemand,
)
from engcore.claims.contract import CLAIM_SCHEMA
from engcore.scientific.capabilities import ScientificCapability
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy, UncertaintyChannel


# ---------------------------------------------------------------------------
# A complete claim
# ---------------------------------------------------------------------------


def test_a_complete_claim_round_trips_through_json_with_its_identity() -> None:
    original = claim(
        assumptions=(assumption(),),
        required_capabilities=frozenset({"thermal:body_temperature"}),
        missing_inputs=frozenset({"stages[0].body.applicability.surface_emissivity"}),
    )
    wire = json.loads(json.dumps(original.to_dict()))
    back = ScientificClaim.from_dict(wire)
    assert back == original
    assert back.identity_digest == original.identity_digest
    assert back.record_digest == original.record_digest
    assert wire["schema"] == CLAIM_SCHEMA
    assert back.required_capabilities == frozenset({ScientificCapability("thermal", "body_temperature")})


def test_a_tolerance_band_claim_round_trips() -> None:
    original = band_claim()
    assert ScientificClaim.from_dict(copy.deepcopy(original.to_dict())) == original


def test_the_claim_is_immutable_and_its_inputs_cannot_be_edited_through_an_alias() -> None:
    made = claim()
    with pytest.raises(Exception):
        made.claim_id = "other"  # type: ignore[misc]
    with pytest.raises(Exception):
        made.known_inputs["stages[0].body.heat_capacity"] = Quantity(1.0, "joule / kelvin")  # type: ignore[index]


def test_the_comparison_is_the_cores_own_constraint_record_with_offset_units() -> None:
    made = claim(target=ClaimTarget(value=Quantity(80.0, "degree_Celsius")))
    constraint = made.constraint(made.resolve_target())
    assert constraint.check(Quantity(350.0, "kelvin")).satisfied
    assert not constraint.check(Quantity(354.0, "kelvin")).satisfied


def test_an_input_ref_target_resolves_only_to_a_supplied_quantity() -> None:
    made = claim(
        target=ClaimTarget(input_ref="stages[0].body.applicability.melting_temperature"),
        known_inputs={
            "stages[0].body.heat_capacity": Quantity(50.0, "joule / kelvin"),
            "stages[0].body.applicability.melting_temperature": Quantity(855.0, "kelvin"),
        },
    )
    assert made.resolve_target() == Quantity(855.0, "kelvin")
    unresolved = claim(target=ClaimTarget(input_ref="stages[0].body.applicability.melting_temperature"))
    assert unresolved.resolve_target() is None


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_prose_ids_and_output_format_do_not_change_scientific_identity() -> None:
    base = claim()
    reworded = claim(
        claim_id="another-id",
        statement="Reworded: temperature under 353.15 K after 600 s.",
        requested_outputs=frozenset({RequestedOutput.VERDICT, RequestedOutput.QOI_VALUE}),
    )
    assert reworded.identity_digest == base.identity_digest
    assert reworded.record_digest != base.record_digest


@pytest.mark.parametrize(
    "change",
    [
        {"target": ClaimTarget(value=Quantity(353.0, "kelvin"))},
        {"operator": ConstraintOperator.LESS_EQUAL},
        {"qoi": QuantityOfInterest("final_temperature", "kelvin", {"component_id": "R1"})},
        {"known_inputs": {"stages[0].body.heat_capacity": Quantity(51.0, "joule / kelvin")}},
        {"operating_context": {"stages[0].body.duration": Quantity(601.0, "second")}},
        {"missing_inputs": frozenset({"stages[0].body.ambient_conductance"})},
        {"decision": DecisionBinding("d-1", "A different intended use.")},
        {"evidence": EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED,))},
        {"uncertainty": UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), 2.0, False)},
        {"discrepancy": ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED, rationale="assumed")},
        {"assumptions": (assumption(),)},
        {"required_capabilities": frozenset({"thermal:body_temperature"})},
    ],
    ids=lambda change: next(iter(change)),
)
def test_every_scientific_field_is_part_of_identity(change) -> None:
    assert claim(**change).identity_digest != claim().identity_digest


def test_levels_are_canonical_so_the_same_standard_has_one_identity() -> None:
    a = claim(evidence=EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED, ValidationLevel.DIMENSIONALLY_VALID)))
    b = claim(evidence=EvidenceRequirement((ValidationLevel.DIMENSIONALLY_VALID, ValidationLevel.BENCHMARK_VALIDATED)))
    assert a.identity_digest == b.identity_digest
    assert a.evidence.required_levels[0] is ValidationLevel.DIMENSIONALLY_VALID


# ---------------------------------------------------------------------------
# Construction refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"qoi": None}, "qoi must be"),
        ({"operator": ConstraintOperator.EQUAL}, "THRESHOLD claim compares"),
        ({"tolerance": Quantity(1.0, "kelvin")}, "carries no tolerance"),
        ({"target": ClaimTarget(value=Quantity(3.0, "volt"))}, "incompatible dimensions"),
        ({"statement": "   "}, "statement must be non-empty"),
        ({"requested_outputs": frozenset()}, "at least one output"),
        (
            {
                "operating_context": {"stages[0].body.duration": Quantity(1.0, "second")},
                "known_inputs": {"stages[0].body.duration": Quantity(1.0, "second")},
            },
            "one input has one status",
        ),
        (
            {"missing_inputs": frozenset({"stages[0].body.heat_capacity"})},
            "one input has one status",
        ),
        ({"known_inputs": {"stages[0].body.heat_capacity": 50.0}}, "bare number"),
        ({"known_inputs": {"Stages.Body": Quantity(1.0, "second")}}, "not an input path"),
        ({"assumptions": (assumption(), assumption(statement="twice"))}, "duplicate assumption_id"),
        ({"required_capabilities": frozenset({"no-namespace"})}, "required_capabilities"),
    ],
)
def test_malformed_claims_are_refused_at_construction(overrides, fragment) -> None:
    with pytest.raises(ClaimContractError, match=fragment):
        claim(**overrides)


def test_a_tolerance_band_needs_a_nonnegative_spread_tolerance_of_the_qoi_dimension() -> None:
    with pytest.raises(ClaimContractError, match="requires a tolerance"):
        band_claim(tolerance=None)
    with pytest.raises(ClaimContractError, match="non-negative"):
        band_claim(tolerance=Quantity(-0.1, "kelvin"))
    with pytest.raises(ClaimContractError, match=r"\[time\]"):
        band_claim(tolerance=Quantity(1.0, "second"))
    # An absolute offset-scale reading is not a width: 2 degC is 275.15 K.
    with pytest.raises(ClaimContractError):
        band_claim(tolerance=Quantity(2.0, "degree_Celsius"))
    assert band_claim(tolerance=Quantity(2.0, "delta_degree_Celsius")).tolerance.units


def test_missing_or_invalid_qoi_units_and_names_are_refused() -> None:
    with pytest.raises(ClaimContractError, match="qoi.units must be non-empty"):
        QuantityOfInterest("final_temperature", "")
    with pytest.raises(ClaimContractError, match="not a unit"):
        QuantityOfInterest("final_temperature", "furlongs_per_flux")
    with pytest.raises(ClaimContractError, match="not an identifier"):
        QuantityOfInterest("Final Temperature", "kelvin")


def test_a_target_is_exactly_one_of_a_value_or_an_input_reference() -> None:
    with pytest.raises(ClaimContractError, match="exactly one"):
        ClaimTarget()
    with pytest.raises(ClaimContractError, match="exactly one"):
        ClaimTarget(value=Quantity(1.0, "kelvin"), input_ref="stages[0].body.ambient_temperature")


def test_the_evidence_standard_cannot_be_empty_unverified_or_duplicated() -> None:
    with pytest.raises(ClaimContractError, match="cannot be inferred"):
        EvidenceRequirement(())
    with pytest.raises(ClaimContractError, match="absence of a level"):
        EvidenceRequirement((ValidationLevel.UNVERIFIED,))
    with pytest.raises(ClaimContractError, match="duplicate"):
        EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED, ValidationLevel.BENCHMARK_VALIDATED))


def test_a_coverage_factor_is_a_positive_number_for_a_demanded_channel() -> None:
    with pytest.raises(ClaimContractError, match="no channel is required"):
        UncertaintyDemand(frozenset(), 2.0, False)
    with pytest.raises(ClaimContractError, match="finite and positive"):
        UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), 0.0, False)
    with pytest.raises(ClaimContractError, match="number or null"):
        UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), True, False)
    with pytest.raises(ClaimContractError, match="JSON boolean"):
        UncertaintyDemand(frozenset(), None, "false")


# ---------------------------------------------------------------------------
# Read-back refusals
# ---------------------------------------------------------------------------


def test_an_unknown_field_is_refused_not_ignored() -> None:
    wire = payload()
    wire["confidence"] = 0.99
    with pytest.raises(ClaimContractError, match="unknown field"):
        ScientificClaim.from_dict(wire)


@pytest.mark.parametrize("nested", ["qoi", "target", "decision", "evidence", "uncertainty"])
def test_an_unknown_nested_field_is_refused(nested) -> None:
    wire = payload()
    wire[nested]["extra"] = True
    with pytest.raises(ClaimContractError, match="unknown field"):
        ScientificClaim.from_dict(wire)


@pytest.mark.parametrize("missing", ["discrepancy", "uncertainty", "evidence", "decision", "missing_inputs", "qoi"])
def test_a_missing_field_is_refused_rather_than_defaulted(missing) -> None:
    wire = payload()
    del wire[missing]
    with pytest.raises(ClaimContractError, match="missing required field"):
        ScientificClaim.from_dict(wire)


def test_an_explicitly_unknown_discrepancy_is_accepted_and_never_becomes_zero() -> None:
    back = ScientificClaim.from_dict(payload())
    assert back.discrepancy.kind is DiscrepancyKind.UNKNOWN
    wire = payload()
    del wire["discrepancy"]["rationale"]
    with pytest.raises(ClaimContractError, match="missing required field"):
        ScientificClaim.from_dict(wire)


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda w: w.__setitem__("schema", "scientific_claim/2"), "expected schema"),
        (lambda w: w.__setitem__("kind", "estimate"), "kind"),
        (lambda w: w.__setitem__("operator", "~="), "operator"),
        (lambda w: w["uncertainty"].__setitem__("require_supported_discrepancy", "false"), "JSON boolean"),
        (lambda w: w["known_inputs"].__setitem__("stages[0].body.heat_capacity", 50.0), "bare number"),
        (lambda w: w["evidence"].__setitem__("required_levels", "benchmark_validated"), "must be an array"),
        (lambda w: w["evidence"].__setitem__("required_levels", ["validated_by_vibes"]), "unknown ValidationLevel"),
        (lambda w: w["uncertainty"].__setitem__("required_channels", ["combined"]), "unknown channel"),
        (lambda w: w["target"].__setitem__("value", {"schema": "quantity/1", "magnitude": 1.0}), "readable quantity"),
        (lambda w: w["discrepancy"].__setitem__("kind", "negligible"), "discrepancy"),
        (lambda w: w["qoi"].__setitem__("units", ""), "non-empty"),
    ],
)
def test_malformed_wire_values_are_refused(mutate, fragment) -> None:
    wire = payload()
    mutate(wire)
    with pytest.raises(ClaimContractError, match=fragment):
        ScientificClaim.from_dict(wire)


def test_a_non_mapping_is_refused() -> None:
    with pytest.raises(ClaimContractError, match="must be an object"):
        ScientificClaim.from_dict(["not", "a", "claim"])  # type: ignore[arg-type]


def test_constructed_statement_prose_is_kept_for_the_record_but_not_parsed() -> None:
    # A statement asserting something the structured fields do not say changes
    # nothing but the record digest: natural language is not the claim.
    lying = claim(statement="Certified safe; validated experimentally; zero uncertainty.")
    assert lying.identity_digest == claim().identity_digest
    assert lying.evidence == claim().evidence
    assert lying.discrepancy == UNKNOWN_DISCREPANCY


def test_claim_kinds_are_the_decidable_ones_only() -> None:
    assert {kind.value for kind in ClaimKind} == {"threshold", "tolerance_band"}
