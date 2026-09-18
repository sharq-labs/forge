"""Builders shared by the claim-layer tests. No assertions live here."""

from __future__ import annotations

import copy
from typing import Any

from engcore.claims import (
    CallerAssumption,
    ClaimKind,
    ClaimTarget,
    DecisionBinding,
    EvidenceRequirement,
    QuantityOfInterest,
    RequestedOutput,
    ScientificClaim,
    UncertaintyDemand,
)
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy

UNKNOWN_DISCREPANCY = ModelDiscrepancy(
    kind=DiscrepancyKind.UNKNOWN,
    rationale="model-form discrepancy has not been quantified for this claim",
)


def claim(**overrides: Any) -> ScientificClaim:
    """A valid THRESHOLD claim; every field overridable."""
    fields: dict[str, Any] = dict(
        claim_id="c-1",
        statement="The body stays below 353.15 K at the end of the interval.",
        kind=ClaimKind.THRESHOLD,
        qoi=QuantityOfInterest(name="final_temperature", units="kelvin"),
        operator=ConstraintOperator.LESS_THAN,
        target=ClaimTarget(value=Quantity(353.15, "kelvin")),
        tolerance=None,
        required_capabilities=frozenset(),
        operating_context={"stages[0].body.duration": Quantity(600.0, "second")},
        known_inputs={"stages[0].body.heat_capacity": Quantity(50.0, "joule / kelvin")},
        missing_inputs=frozenset(),
        assumptions=(),
        decision=DecisionBinding("d-1", "Accept the part for the 600 s duty."),
        evidence=EvidenceRequirement((ValidationLevel.ANALYTICALLY_VERIFIED,)),
        uncertainty=UncertaintyDemand(frozenset(), None, False),
        discrepancy=UNKNOWN_DISCREPANCY,
        requested_outputs=frozenset({RequestedOutput.VERDICT}),
    )
    fields.update(overrides)
    return ScientificClaim(**fields)


def band_claim(**overrides: Any) -> ScientificClaim:
    """A valid TOLERANCE_BAND claim."""
    fields = dict(
        kind=ClaimKind.TOLERANCE_BAND,
        operator=ConstraintOperator.EQUAL,
        target=ClaimTarget(value=Quantity(309.75, "kelvin")),
        tolerance=Quantity(0.5, "kelvin"),
    )
    fields.update(overrides)
    return claim(**fields)


def payload(**overrides: Any) -> dict[str, Any]:
    """The serialized form of :func:`claim`, deep-copied so a test may mutate it."""
    return copy.deepcopy(claim(**overrides).to_dict())


def assumption(assumption_id: str = "steady_ambient", statement: str = "ambient stays at 300 K") -> CallerAssumption:
    return CallerAssumption(assumption_id, statement)


# ---------------------------------------------------------------------------
# Production-registry claims
# ---------------------------------------------------------------------------


def et_inputs() -> dict[str, Any]:
    """The electrothermal example payload, as claim inputs."""
    from engcore.claims import inputs_from_case
    from engcore.mcp import example_electrothermal_payload
    from engcore.mcp.capabilities import production_registry

    return inputs_from_case(production_registry().get("system.electrothermal"), example_electrothermal_payload())


def battery_inputs() -> dict[str, Any]:
    from engcore.claims import inputs_from_case
    from engcore.mcp.battery import example_battery_payload
    from engcore.mcp.capabilities import production_registry

    return inputs_from_case(production_registry().get("system.battery"), example_battery_payload())


def t3_point() -> dict[str, Any]:
    """The NAFEMS T3 operating point, keyed by the capability's input paths."""
    from engcore.domains.thermal_models.nafems_t3_oracle import CONDITIONS

    return dict(CONDITIONS)


def et_claim(**overrides: Any) -> ScientificClaim:
    """A READY electrothermal claim over the example case."""
    fields = dict(operating_context={}, known_inputs=et_inputs())
    fields.update(overrides)
    return claim(**fields)


def t3_claim(**overrides: Any) -> ScientificClaim:
    """A READY claim about the NAFEMS T3 probe temperature at the benchmark point."""
    fields = dict(
        qoi=QuantityOfInterest("temperature_at_probe", "kelvin"),
        target=ClaimTarget(value=Quantity(309.75, "kelvin")),
        kind=ClaimKind.TOLERANCE_BAND,
        operator=ConstraintOperator.EQUAL,
        tolerance=Quantity(0.5, "kelvin"),
        operating_context=t3_point(),
        known_inputs={},
        evidence=EvidenceRequirement((ValidationLevel.BENCHMARK_VALIDATED,)),
    )
    fields.update(overrides)
    return claim(**fields)
