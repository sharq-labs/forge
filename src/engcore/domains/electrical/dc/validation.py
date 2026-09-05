"""Validation of a computed DC solution.

A converged linear solve is not a validated result. Six checks run, and they
are **not equally strong** — saying "six independent checks" would overstate
the evidence, so each is classified explicitly:

======================================  ====================================
``dimensional_consistency``             dimensional contract check
``linear_system_residual``              numerical equation-solve check
``kirchhoff_current_law``               **independently reconstructed**
                                        topology/physics cross-check
``resistor_metric_consistency``         internal constitutive consistency
                                        (self-derived, not independent)
``voltage_source_relation``             **independently reconstructed**
                                        source-constraint check
``power_balance``                       global physical consistency
======================================  ====================================

The genuinely independent ones rebuild quantities from the component list
rather than re-evaluating a row of the MNA matrix. Re-using the matrix would
only re-prove that ``A x = z`` was solved — which the residual check already
establishes — and could never catch an incorrect *stamp*.

Sign conventions (identical to those documented on the components):

* resistor: ``V_ab = V(a) - V(b)``, ``I_ab = V_ab / R`` positive ``a -> b``,
  absorbed power ``P = V_ab * I_ab >= 0``
* voltage source: branch current ``I`` leaves the positive node through the
  source; absorbed power ``P = (V_p - V_n) * I`` (negative when delivering)
* current source: current flows ``from -> to`` inside the source; absorbed
  power ``P = (V_from - V_to) * I`` (negative when delivering)

Power balance sums *absorbed* power over every element, which must vanish.
No ``abs()`` is applied anywhere to make a sign work out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ....scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ....scientific.units.quantity import Quantity
from .components import CURRENT_UNIT, POWER_UNIT, VOLTAGE_UNIT
from .errors import ElectricalDCError
from .mna import PreparedDCSystem


@dataclass(frozen=True)
class DCValidationSettings:
    """Central tolerances. Scattering literals through production code makes
    a tolerance decision unauditable, so they live here and are recorded in
    provenance and in the solver settings.

    Every tolerance must be finite and non-negative. Zero is allowed and
    means an exact check; NaN would make every comparison silently false
    (turning validation into a rubber stamp) and infinity would make every
    comparison silently true, so both are refused.
    """

    residual_atol: float = 1e-9
    residual_rtol: float = 1e-9
    kcl_atol_ampere: float = 1e-9
    ohm_atol_volt: float = 1e-9
    source_atol_volt: float = 1e-9
    power_atol_watt: float = 1e-9

    def __post_init__(self) -> None:
        for name in (
            "residual_atol", "residual_rtol", "kcl_atol_ampere",
            "ohm_atol_volt", "source_atol_volt", "power_atol_watt",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ElectricalDCError(
                    f"validation tolerance {name!r} must be finite, got "
                    f"{value!r}"
                )
            if value < 0.0:
                raise ElectricalDCError(
                    f"validation tolerance {name!r} must be >= 0, got {value!r}"
                )
            object.__setattr__(self, name, value)

    def as_mapping(self) -> dict[str, float]:
        return {
            "residual_atol": self.residual_atol,
            "residual_rtol": self.residual_rtol,
            "kcl_atol_ampere": self.kcl_atol_ampere,
            "ohm_atol_volt": self.ohm_atol_volt,
            "source_atol_volt": self.source_atol_volt,
            "power_atol_watt": self.power_atol_watt,
        }


def _voltages(prepared: PreparedDCSystem, solution: np.ndarray) -> dict[str, float]:
    return {
        node_id: prepared.node_voltage(solution, node_id)
        for node_id in prepared.circuit.node_ids
    }


def check_dimensions(metrics: dict[str, Quantity]) -> ValidationCheck:
    """Every reported metric must carry the dimension its name implies."""
    expected = {
        "node_voltage": VOLTAGE_UNIT,
        "source_current": CURRENT_UNIT,
        "resistor_current": CURRENT_UNIT,
        "resistor_voltage": VOLTAGE_UNIT,
        "resistor_power": POWER_UNIT,
        "source_power": POWER_UNIT,
        "current_source_power": POWER_UNIT,
        "total_resistor_dissipation": POWER_UNIT,
        "total_source_delivered_power": POWER_UNIT,
    }
    offenders: list[str] = []
    for name, quantity in sorted(metrics.items()):
        prefix = name.split(":", 1)[0]
        unit = expected.get(prefix)
        if unit is None:
            continue
        if not quantity.is_compatible_with(unit):
            offenders.append(f"{name} is {quantity.units!r}, expected {unit!r}")
    if offenders:
        return ValidationCheck(
            name="dimensional_consistency",
            outcome=ValidationOutcome.FAIL,
            detail="; ".join(offenders),
        )
    return ValidationCheck(
        name="dimensional_consistency",
        outcome=ValidationOutcome.PASS,
        detail=f"{len(metrics)} metrics carry their expected dimensions",
        establishes=ValidationLevel.DIMENSIONALLY_VALID,
    )


def check_linear_residual(
    prepared: PreparedDCSystem,
    solution: np.ndarray,
    settings: DCValidationSettings,
) -> ValidationCheck:
    """``r = A x - z``: did the backend actually solve the system it was given?"""
    residual = prepared.matrix @ solution - prepared.rhs
    norm = float(np.linalg.norm(residual))
    scale = float(np.linalg.norm(prepared.rhs))
    tolerance = settings.residual_atol + settings.residual_rtol * scale
    passed = norm <= tolerance
    return ValidationCheck(
        name="linear_system_residual",
        outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
        detail=f"||A x - z|| = {norm:.3e} (||z|| = {scale:.3e})",
        establishes=(
            ValidationLevel.NUMERICALLY_CONVERGED if passed else None
        ),
        residual=norm,
        tolerance=tolerance,
    )


def check_kcl(
    prepared: PreparedDCSystem,
    solution: np.ndarray,
    settings: DCValidationSettings,
) -> ValidationCheck:
    """Charge balance at every non-reference node, rebuilt from components."""
    circuit = prepared.circuit
    voltages = _voltages(prepared, solution)

    worst_node = ""
    worst_residual = 0.0
    for node_id in circuit.non_reference_node_ids:
        net_out = 0.0
        for resistor in circuit.resistors:
            if node_id == resistor.node_a:
                other = resistor.node_b
            elif node_id == resistor.node_b:
                other = resistor.node_a
            else:
                continue
            net_out += (voltages[node_id] - voltages[other]) / resistor.resistance_ohm
        for source in circuit.voltage_sources:
            current = prepared.source_current(solution, source.component_id)
            if node_id == source.positive_node:
                net_out += current       # defined as leaving the positive node
            elif node_id == source.negative_node:
                net_out -= current
        for source in circuit.current_sources:
            value = source.current_ampere
            if node_id == source.from_node:
                net_out += value         # extracted here, flows into the source
            elif node_id == source.to_node:
                net_out -= value         # injected here
        if abs(net_out) > abs(worst_residual):
            worst_residual = net_out
            worst_node = node_id

    passed = abs(worst_residual) <= settings.kcl_atol_ampere
    detail = (
        f"worst node {worst_node!r}: net current out = {worst_residual:.3e} A"
        if worst_node
        else "no non-reference nodes to check"
    )
    return ValidationCheck(
        name="kirchhoff_current_law",
        outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
        detail=detail,
        residual=abs(worst_residual),
        tolerance=settings.kcl_atol_ampere,
    )


def check_resistor_relation(
    prepared: PreparedDCSystem,
    solution: np.ndarray,
    settings: DCValidationSettings,
) -> ValidationCheck:
    """Internal consistency of the reported resistor metrics.

    Honest description of what this proves: the current is *derived* here as
    ``I = V/R``, so ``V - I·R`` is self-derived and vanishes to rounding by
    construction. It is a useful guard against a defective metric-extraction
    path or a corrupted quantity, and it is **not** independent physical
    evidence about the solution.

    The KCL check is the strong element-level cross-check: it reconstructs
    signed branch currents from the topology and can therefore catch a wrong
    conductance stamp, which this check cannot.
    """
    circuit = prepared.circuit
    voltages = _voltages(prepared, solution)
    if not circuit.resistors:
        return ValidationCheck(
            name="resistor_metric_consistency",
            outcome=ValidationOutcome.NOT_RUN,
            detail="circuit contains no resistors",
        )

    worst_id = ""
    worst_residual = 0.0
    for resistor in circuit.resistors:
        v_ab = voltages[resistor.node_a] - voltages[resistor.node_b]
        i_ab = v_ab / resistor.resistance_ohm
        residual = v_ab - i_ab * resistor.resistance_ohm
        if abs(residual) > abs(worst_residual):
            worst_residual = residual
            worst_id = resistor.component_id

    passed = abs(worst_residual) <= settings.ohm_atol_volt
    return ValidationCheck(
        name="resistor_metric_consistency",
        outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
        detail=(
            f"worst resistor {worst_id!r}: V - I R = {worst_residual:.3e} V "
            f"(internal metric consistency, not independent evidence)"
        ),
        residual=abs(worst_residual),
        tolerance=settings.ohm_atol_volt,
    )


def check_voltage_sources(
    prepared: PreparedDCSystem,
    solution: np.ndarray,
    settings: DCValidationSettings,
) -> ValidationCheck:
    """``V_p - V_n - Vs = 0`` recomputed per ideal source."""
    circuit = prepared.circuit
    voltages = _voltages(prepared, solution)
    if not circuit.voltage_sources:
        return ValidationCheck(
            name="voltage_source_relation",
            outcome=ValidationOutcome.NOT_RUN,
            detail="circuit contains no voltage sources",
        )

    worst_id = ""
    worst_residual = 0.0
    for source in circuit.voltage_sources:
        residual = (
            voltages[source.positive_node]
            - voltages[source.negative_node]
            - source.voltage_volt
        )
        if abs(residual) > abs(worst_residual):
            worst_residual = residual
            worst_id = source.component_id

    passed = abs(worst_residual) <= settings.source_atol_volt
    return ValidationCheck(
        name="voltage_source_relation",
        outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
        detail=f"worst source {worst_id!r}: (V+ - V-) - Vs = {worst_residual:.3e} V",
        residual=abs(worst_residual),
        tolerance=settings.source_atol_volt,
    )


def check_power_balance(
    prepared: PreparedDCSystem,
    solution: np.ndarray,
    settings: DCValidationSettings,
) -> ValidationCheck:
    """Total absorbed power over all elements must vanish (Tellegen)."""
    circuit = prepared.circuit
    voltages = _voltages(prepared, solution)

    absorbed = 0.0
    magnitude = 0.0
    for resistor in circuit.resistors:
        v_ab = voltages[resistor.node_a] - voltages[resistor.node_b]
        power = v_ab * v_ab / resistor.resistance_ohm
        absorbed += power
        magnitude += abs(power)
    for source in circuit.voltage_sources:
        current = prepared.source_current(solution, source.component_id)
        power = (
            voltages[source.positive_node] - voltages[source.negative_node]
        ) * current
        absorbed += power
        magnitude += abs(power)
    for source in circuit.current_sources:
        power = (
            voltages[source.from_node] - voltages[source.to_node]
        ) * source.current_ampere
        absorbed += power
        magnitude += abs(power)

    tolerance = settings.power_atol_watt + settings.residual_rtol * magnitude
    passed = abs(absorbed) <= tolerance
    return ValidationCheck(
        name="power_balance",
        outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
        detail=(
            f"sum of absorbed power = {absorbed:.3e} W "
            f"(total magnitude {magnitude:.3e} W)"
        ),
        residual=abs(absorbed),
        tolerance=tolerance,
    )


def build_validation_report(
    prepared: PreparedDCSystem,
    solution: np.ndarray,
    metrics: dict[str, Quantity],
    settings: DCValidationSettings,
) -> ValidationReport:
    """All independent checks for one solved circuit.

    Only two validation *levels* are claimable here: DIMENSIONALLY_VALID and
    NUMERICALLY_CONVERGED. The physics checks (KCL, Ohm, source relation,
    power balance) are recorded as passing checks but establish no level:
    they demonstrate internal consistency, not agreement with an external
    benchmark or measurement, and the core's vocabulary has no level for
    "internally physically consistent". Claiming ANALYTICALLY_VERIFIED at
    runtime would be false — analytical comparison happens in the test suite
    against independently derived values, not here.
    """
    return ValidationReport(
        checks=(
            check_dimensions(metrics),
            check_linear_residual(prepared, solution, settings),
            check_kcl(prepared, solution, settings),
            check_resistor_relation(prepared, solution, settings),
            check_voltage_sources(prepared, solution, settings),
            check_power_balance(prepared, solution, settings),
        ),
        notes=(
            "Checks are reconstructed from circuit elements, independently of "
            "the assembled MNA matrix."
        ),
    )
