"""Provider-neutral uncertainty propagation through deterministic mappings.

This module owns only the generic arithmetic needed when a typed scientific
quantity crosses a deterministic mapping. It does not decide whether evidence
is attributable, independent, validated, or otherwise scientifically
admissible; those higher-level decisions remain in the UQ/credibility layers.

Keeping this primitive in the Scientific layer lets execution propagate a
declared uncertainty without depending upward on engcore.uq.
"""

from __future__ import annotations

import math

from ..composition.conversion import EnergyConversion
from ..composition.transfer import BUDGET_TOLERANCE
from ..errors import InvalidScientificProblem
from ..units.quantity import Quantity, base_unit, is_ratio_scale
from ..units.validation import require_same_dimension
from .uncertainty import Uncertainty, UncertaintyKind


def _agree_relatively(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right))
    return abs(left - right) <= BUDGET_TOLERANCE * scale


def _delta_magnitude_in(value: Quantity, unit: str) -> float:
    """Convert an uncertainty width using scale only, never an absolute offset."""
    require_same_dimension(
        value,
        Quantity(1.0, unit),
        context="uncertainty delta conversion",
    )
    one = Quantity(1.0, value.units).magnitude_in(unit)
    zero = Quantity(0.0, value.units).magnitude_in(unit)
    return float(value.magnitude) * abs(one - zero)


def _require_interval_contains_value(
    value: Quantity,
    uncertainty: Uncertainty,
    *,
    context: str,
) -> None:
    lower, upper = uncertainty.lower, uncertainty.upper
    if lower is None or upper is None:
        return
    require_same_dimension(value, lower, context=context)
    unit = lower.units
    magnitude = value.magnitude_in(unit)
    low = lower.magnitude_in(unit)
    high = upper.magnitude_in(unit)
    if not (
        low <= magnitude <= high
        or _agree_relatively(magnitude, low)
        or _agree_relatively(magnitude, high)
    ):
        raise InvalidScientificProblem(
            f"{context}: interval [{low}, {high}] {unit} does not contain "
            f"{magnitude} {unit}, the value whose uncertainty it claims to bound"
        )


def propagate_declared_mapping_uncertainty(
    source_value: Quantity,
    target_value: Quantity,
    source_uncertainty: Uncertainty,
    *,
    source_label: str,
    target_label: str,
    instant: str,
    conversion: EnergyConversion | None = None,
    attribution: str | None = None,
) -> Uncertainty:
    """Propagate uncertainty through one declared deterministic mapping.

    UNKNOWN stays UNKNOWN. STANDARD widths are converted as deltas and scaled
    by deterministic conversion efficiency. A declared standard uncertainty of
    efficiency is combined in quadrature, with that independence assumption
    stated explicitly. INTERVAL bounds retain absolute-value conversion
    semantics and never silently absorb efficiency uncertainty.
    """
    if not isinstance(source_value, Quantity) or not isinstance(target_value, Quantity):
        raise InvalidScientificProblem(
            "cross-domain uncertainty propagation requires typed source and target values"
        )
    if not isinstance(source_uncertainty, Uncertainty):
        raise InvalidScientificProblem(
            "cross-domain uncertainty propagation requires Uncertainty"
        )

    source_label = str(source_label).strip()
    target_label = str(target_label).strip()
    instant = str(instant).strip()
    if not source_label or not target_label or not instant:
        raise InvalidScientificProblem(
            "cross-domain uncertainty propagation requires source, target and instant identities"
        )

    require_same_dimension(
        source_value,
        target_value,
        context="cross-domain mapped value",
    )

    if conversion is not None:
        if not isinstance(conversion, EnergyConversion):
            raise InvalidScientificProblem(
                "cross-domain conversion must be EnergyConversion"
            )
        outcome = conversion.convert(source_value)
        if outcome.value is None:
            raise InvalidScientificProblem(
                f"cannot propagate uncertainty across conversion {conversion.name!r}: "
                f"{outcome.reason}"
            )
        expected = outcome.value.magnitude_in(target_value.units)
        actual = target_value.magnitude
        if not _agree_relatively(expected, actual):
            raise InvalidScientificProblem(
                f"cross-domain mapped target {actual} {target_value.units} does not "
                f"match conversion {conversion.name!r}, which gives "
                f"{expected} {target_value.units}"
            )

    if source_uncertainty.kind is UncertaintyKind.INTERVAL:
        _require_interval_contains_value(
            source_value,
            source_uncertainty,
            context=f"uncertainty of {source_label}",
        )

    method_prefix = (
        "cross_domain_transport"
        if conversion is None
        else f"cross_domain_conversion:{conversion.name}"
    )
    source_attribution = (
        str(attribution).strip()
        if attribution is not None
        else f"coupling:{source_label}->{target_label}|from:{source_uncertainty.source}"
    )

    if source_uncertainty.kind is UncertaintyKind.UNKNOWN:
        return Uncertainty.unknown(
            notes=(
                f"uncertainty remained unknown while transferring "
                f"{source_label} -> {target_label} at {instant}; "
                f"source said: {source_uncertainty.notes or 'not evaluated'}"
            )
        )

    factor = 1.0 if conversion is None else float(conversion.efficiency)
    source_unit = source_value.units
    target_unit = target_value.units
    efficiency_width = (
        None if conversion is None else conversion.efficiency_uncertainty
    )

    if source_uncertainty.kind is UncertaintyKind.STANDARD:
        standard = source_uncertainty.standard_uncertainty
        assert standard is not None
        require_same_dimension(
            standard,
            source_value,
            context="cross-domain standard uncertainty",
        )
        source_delta = _delta_magnitude_in(standard, source_unit) * abs(factor)
        efficiency_note = (
            "conversion has no efficiency uncertainty"
            if conversion is None
            else "conversion efficiency treated as deterministic because the "
                 "conversion record carries no uncertainty for it"
        )
        if efficiency_width is not None:
            entering = source_value.magnitude_in(source_unit)
            if entering != 0.0:
                relative_input = (
                    _delta_magnitude_in(standard, source_unit) / abs(entering)
                )
                relative_efficiency = efficiency_width / abs(factor)
                combined = math.sqrt(
                    relative_input ** 2 + relative_efficiency ** 2
                )
                source_delta = combined * abs(entering * factor)
            efficiency_note = (
                f"declared efficiency uncertainty {efficiency_width} was combined "
                f"in quadrature with the input uncertainty; this records an "
                f"independence assumption, it does not establish independence"
            )

        # A standard uncertainty is a spread, and an absolute affine coordinate
        # (degC, degF) cannot state one. A target on such a scale carries the
        # spread on the dimension's base unit instead, converted by slope only.
        spread_unit = target_unit if is_ratio_scale(target_unit) else base_unit(target_unit)
        propagated = Quantity(
            _delta_magnitude_in(Quantity(source_delta, source_unit), spread_unit),
            spread_unit,
        )
        return Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=propagated,
            source=source_attribution,
            source_kind=source_uncertainty.source_kind,
            method=(
                method_prefix
                if efficiency_width is None
                else f"{method_prefix}+efficiency_uncertainty_in_quadrature"
            ),
            notes=(
                f"propagated from "
                f"{source_uncertainty.method or 'declared source method'}; "
                f"standard uncertainty converted as a delta (scale only); "
                f"{efficiency_note}"
            ),
        )

    if source_uncertainty.kind is UncertaintyKind.INTERVAL:
        lower, upper = source_uncertainty.lower, source_uncertainty.upper
        assert lower is not None and upper is not None
        require_same_dimension(
            lower, source_value, context="cross-domain interval lower"
        )
        require_same_dimension(
            upper, source_value, context="cross-domain interval upper"
        )
        low_mag = lower.magnitude_in(source_unit) * factor
        high_mag = upper.magnitude_in(source_unit) * factor
        lo, hi = sorted((low_mag, high_mag))
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(lo, source_unit).to(target_unit),
            upper=Quantity(hi, source_unit).to(target_unit),
            confidence_level=source_uncertainty.confidence_level,
            source=source_attribution,
            source_kind=source_uncertainty.source_kind,
            method=method_prefix,
            notes=(
                f"propagated interval from "
                f"{source_uncertainty.method or 'declared source method'}; "
                "no distribution or correlation was inferred, so a declared "
                "efficiency uncertainty is not combined into interval bounds"
            ),
        )

    raise InvalidScientificProblem(
        f"unsupported uncertainty kind {source_uncertainty.kind!r}"
    )
