"""Electrical DC V0 — linear resistive steady-state circuit analysis.

Scope: resistors, ideal independent DC voltage and current sources, and an
explicitly declared reference node. Solved by modified nodal analysis over
SciPy's dense linear solve.

Not in scope: capacitors, inductors, transients, AC/frequency domain,
diodes, transistors, dependent sources, SPICE netlists, distributed effects.
This is a validated linear resistive DC analysis domain; it is not a SPICE
replacement.
"""

from .circuit import CANONICAL_SCHEMA, DOMAIN_ARTIFACT_TYPE, DCCircuit
from .components import (
    DCCurrentSource,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from .errors import CircuitBindingError, ElectricalDCError
from .mna import PreparedDCSystem, assemble
from .models import (
    DC_MODELS,
    ELECTRICAL_DC_LINEAR,
    IDEAL_CURRENT_SOURCE_MODEL,
    IDEAL_VOLTAGE_SOURCE_MODEL,
    KCL_MODEL,
    RESISTOR_OHM_MODEL,
    assumptions_for_models,
    build_dc_model_registry,
    dc_solver_capabilities,
    models_for_circuit,
)
from .problem import (
    build_dc_problem,
    current_source_relation_problem,
    problem_fingerprint,
    resistor_relation_problem,
    verify_problem_matches_circuit,
    voltage_source_relation_problem,
)
from .solver import ElectricalDCSolver, solve_circuit
from .validation import DCValidationSettings, build_validation_report

__all__ = [
    "DCCircuit",
    "ElectricalNode",
    "Resistor",
    "DCVoltageSource",
    "DCCurrentSource",
    "PreparedDCSystem",
    "assemble",
    "CANONICAL_SCHEMA",
    "DOMAIN_ARTIFACT_TYPE",
    "CircuitBindingError",
    "DC_MODELS",
    "RESISTOR_OHM_MODEL",
    "KCL_MODEL",
    "IDEAL_VOLTAGE_SOURCE_MODEL",
    "IDEAL_CURRENT_SOURCE_MODEL",
    "models_for_circuit",
    "assumptions_for_models",
    "ELECTRICAL_DC_LINEAR",
    "build_dc_model_registry",
    "dc_solver_capabilities",
    "build_dc_problem",
    "verify_problem_matches_circuit",
    "problem_fingerprint",
    "resistor_relation_problem",
    "voltage_source_relation_problem",
    "current_source_relation_problem",
    "ElectricalDCSolver",
    "ElectricalDCError",
    "solve_circuit",
    "DCValidationSettings",
    "build_validation_report",
]
