"""Mapping: DCCircuit -> ScientificProblem.

The universal IR describes *what is being computed*; the circuit describes
*how the system is wired*. This module translates the former from the latter
without smuggling topology into the IR: the problem carries the quantities
and their units, the model references and the required capabilities, while
connectivity travels to the solver through the prepared-solve payload.

Naming convention for the IR entries (stable, machine-parseable):

===========================  ===========================================
``V:<node_id>``              variable, volt, OBSERVABLE — node potential
``I:<vsource_id>``           variable, ampere, OBSERVABLE — branch current
``R:<resistor_id>``          parameter, ohm — element resistance
``Vs:<vsource_id>``          parameter, volt — imposed source voltage
``Is:<isource_id>``          parameter, ampere — imposed source current
``reference_node``           parameter, categorical — declared datum
``analysis_type``            parameter, categorical — ``dc_steady_state``
===========================  ===========================================

Node voltages and source currents are OBSERVABLE, not DESIGN: nothing in a
DC analysis is free to be chosen. A future study that *does* vary a
resistance would add that resistance as a DESIGN variable; the analysis
problem itself has none.
"""

from __future__ import annotations

from ....scientific.ir.problem import ModelReference, ScientificProblem
from ....scientific.ir.values import CategoricalValue
from ....scientific.ir.variables import (
    ScientificParameter,
    ScientificVariable,
    VariableRole,
)
from .circuit import CANONICAL_SCHEMA, DOMAIN_ARTIFACT_TYPE, DCCircuit
from .components import CURRENT_UNIT, RESISTANCE_UNIT, VOLTAGE_UNIT
from .errors import CircuitBindingError
from .models import ELECTRICAL_DC_LINEAR, models_for_circuit

ANALYSIS_TYPE = "dc_steady_state"

# Problem-metadata keys carrying domain artifact identity.
DOMAIN_ARTIFACT_TYPE_KEY = "domain_artifact_type"
DOMAIN_ARTIFACT_FINGERPRINT_KEY = "domain_artifact_fingerprint"
DOMAIN_ARTIFACT_SCHEMA_KEY = "domain_artifact_schema"
DOMAIN_ARTIFACT_LABEL_KEY = "domain_artifact_label"


def node_voltage_name(node_id: str) -> str:
    return f"V:{node_id}"


def source_current_name(component_id: str) -> str:
    return f"I:{component_id}"


def resistance_name(component_id: str) -> str:
    return f"R:{component_id}"


def source_voltage_name(component_id: str) -> str:
    return f"Vs:{component_id}"


def source_current_value_name(component_id: str) -> str:
    return f"Is:{component_id}"


def build_dc_problem(
    circuit: DCCircuit,
    *,
    problem_id: str | None = None,
    objectives=(),
    constraints=(),
) -> ScientificProblem:
    """Build the universal problem statement for a DC circuit analysis.

    ``objectives`` and ``constraints`` are supplied by the caller only —
    a plain analysis declares none, and the domain never invents them.
    """
    variables: list[ScientificVariable] = []
    parameters: list[ScientificParameter] = []

    # Unknowns of the analysis: every non-reference node potential.
    for node_id in circuit.non_reference_node_ids:
        variables.append(
            ScientificVariable(
                name=node_voltage_name(node_id),
                unit=VOLTAGE_UNIT,
                role=VariableRole.OBSERVABLE,
                description=f"Potential of node {node_id!r} w.r.t. the reference",
            )
        )

    # One additional unknown per ideal voltage source (its branch current).
    for source in circuit.ordered_voltage_sources:
        variables.append(
            ScientificVariable(
                name=source_current_name(source.component_id),
                unit=CURRENT_UNIT,
                role=VariableRole.OBSERVABLE,
                description=(
                    f"Current leaving the positive node through "
                    f"{source.component_id!r}"
                ),
            )
        )

    # Configured element values are parameters, carrying their units.
    for resistor in sorted(circuit.resistors, key=lambda r: r.component_id):
        parameters.append(
            ScientificParameter(
                name=resistance_name(resistor.component_id),
                value=resistor.resistance,
                description=(
                    f"Resistance of {resistor.component_id!r} between "
                    f"{resistor.node_a!r} and {resistor.node_b!r}"
                ),
            )
        )
    for source in circuit.ordered_voltage_sources:
        parameters.append(
            ScientificParameter(
                name=source_voltage_name(source.component_id),
                value=source.voltage,
                description=(
                    f"Imposed voltage of {source.component_id!r}: "
                    f"V({source.positive_node}) - V({source.negative_node})"
                ),
            )
        )
    for source in sorted(circuit.current_sources, key=lambda s: s.component_id):
        parameters.append(
            ScientificParameter(
                name=source_current_value_name(source.component_id),
                value=source.current,
                description=(
                    f"Imposed current of {source.component_id!r}: "
                    f"{source.from_node} -> {source.to_node}"
                ),
            )
        )

    # Typed categorical parameters: the datum and the analysis regime are
    # scientific facts about the problem, not metadata.
    parameters.append(
        ScientificParameter(
            name="reference_node",
            value=CategoricalValue(
                circuit.reference_node,
                vocabulary=tuple(sorted(circuit.node_ids)),
            ),
            description="Explicitly declared voltage datum",
        )
    )
    parameters.append(
        ScientificParameter(
            name="analysis_type",
            value=CategoricalValue(
                ANALYSIS_TYPE, vocabulary=(ANALYSIS_TYPE,)
            ),
            description="Linear steady-state DC analysis",
        )
    )

    return ScientificProblem(
        problem_id=problem_id or f"electrical_dc:{circuit.circuit_id}",
        name=f"DC analysis of circuit {circuit.circuit_id!r}",
        description=circuit.description or (
            "Linear resistive DC steady-state analysis by modified nodal "
            "analysis."
        ),
        variables=tuple(variables),
        parameters=tuple(parameters),
        objectives=tuple(objectives),
        constraints=tuple(constraints),
        # Only the models this circuit actually invokes.
        models=tuple(
            ModelReference(model.model_id, model.version)
            for model in models_for_circuit(circuit)
        ),
        required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
        validation_requirements=frozenset(
            {
                "dimensional_consistency",
                "linear_system_residual",
                "kirchhoff_current_law",
                "resistor_metric_consistency",
                "voltage_source_relation",
                "power_balance",
            }
        ),
        # Identity, not hidden science: the scientific values all live in
        # typed IR fields above. This records *which* circuit artifact those
        # values were taken from, so a problem can never be paired with a
        # different circuit without detection.
        metadata={
            DOMAIN_ARTIFACT_TYPE_KEY: DOMAIN_ARTIFACT_TYPE,
            DOMAIN_ARTIFACT_FINGERPRINT_KEY: circuit.fingerprint(),
            DOMAIN_ARTIFACT_SCHEMA_KEY: CANONICAL_SCHEMA,
            DOMAIN_ARTIFACT_LABEL_KEY: circuit.circuit_id,
        },
    )


def problem_fingerprint(problem: ScientificProblem) -> str | None:
    """The circuit fingerprint a problem claims, if any."""
    value = problem.metadata.get(DOMAIN_ARTIFACT_FINGERPRINT_KEY)
    return str(value) if value is not None else None


def verify_problem_matches_circuit(
    problem: ScientificProblem, circuit: DCCircuit
) -> None:
    """Prove that a problem and a circuit describe the same physical system.

    Raises :class:`CircuitBindingError` on any disagreement. This runs before
    assembly and before any numerical work: a result whose provenance
    contradicts the circuit that produced it is worse than no result at all.

    The problem is never silently rebuilt and the circuit is never silently
    replaced — only the caller knows which artifact is the correct one.
    """
    artifact_type = problem.metadata.get(DOMAIN_ARTIFACT_TYPE_KEY)
    if artifact_type != DOMAIN_ARTIFACT_TYPE:
        raise CircuitBindingError(
            f"problem {problem.problem_id!r} does not describe an "
            f"{DOMAIN_ARTIFACT_TYPE} (found {artifact_type!r}); it was not "
            f"built by build_dc_problem()"
        )

    expected = problem_fingerprint(problem)
    actual = circuit.fingerprint()
    if expected != actual:
        raise CircuitBindingError(
            f"circuit/problem mismatch for problem {problem.problem_id!r}: "
            f"problem expects circuit fingerprint {_short(expected)}, but the "
            f"supplied circuit {circuit.circuit_id!r} has {_short(actual)}. "
            f"They describe different physical systems; rebuild the problem "
            f"from this circuit or supply the matching circuit."
        )


def _short(fingerprint: str | None) -> str:
    """Enough of a digest to identify it in an error, without dumping a
    serialized circuit into a traceback."""
    if not fingerprint:
        return "<none>"
    return f"{fingerprint[:12]}…"


def resistor_relation_problem(resistor) -> ScientificProblem:
    """A one-element problem stating a resistor's constitutive relation.

    Used to *bind* :data:`RESISTOR_OHM_MODEL` to a concrete component: the
    model declares generic physical names (``resistance``,
    ``voltage_across``) while a circuit problem necessarily uses per-instance
    names, so binding is verified per component rather than circuit-wide.
    """
    return ScientificProblem(
        problem_id=f"electrical_dc_resistor:{resistor.component_id}",
        name=f"Constitutive relation of resistor {resistor.component_id!r}",
        variables=(
            ScientificVariable(
                name="voltage_across",
                unit=VOLTAGE_UNIT,
                role=VariableRole.OBSERVABLE,
            ),
        ),
        parameters=(
            ScientificParameter(name="resistance", value=resistor.resistance),
        ),
        models=(
            ModelReference("electrical.dc.resistor_ohm", "0.1.0"),
        ),
        required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    )


def voltage_source_relation_problem(source) -> ScientificProblem:
    """A one-element problem stating an ideal source's imposed relation."""
    return ScientificProblem(
        problem_id=f"electrical_dc_vsource:{source.component_id}",
        name=f"Imposed relation of voltage source {source.component_id!r}",
        variables=(
            ScientificVariable(
                name="terminal_voltage",
                unit=VOLTAGE_UNIT,
                role=VariableRole.OBSERVABLE,
            ),
        ),
        parameters=(
            ScientificParameter(name="source_voltage", value=source.voltage),
        ),
        models=(
            ModelReference("electrical.dc.ideal_voltage_source", "0.1.0"),
        ),
        required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    )


def current_source_relation_problem(source) -> ScientificProblem:
    """A one-element problem stating an ideal current source's imposed relation.

    The missing third of the set. The two siblings above existed because
    ``check_against`` matches input names exactly, so a reusable model can only
    be bound to a circuit one component at a time; the current source's model
    needs the same treatment for the same reason, and its declared
    *unlimited compliance voltage* is now a bounded condition rather than only
    a sentence.

    Note the asymmetry with the voltage source, which is the physics and not an
    oversight: the imposed quantity is the current and the observable is the
    terminal voltage the surrounding network develops.
    """
    return ScientificProblem(
        problem_id=f"electrical_dc_isource:{source.component_id}",
        name=f"Imposed relation of current source {source.component_id!r}",
        variables=(
            ScientificVariable(
                name="terminal_voltage",
                unit=VOLTAGE_UNIT,
                role=VariableRole.OBSERVABLE,
            ),
        ),
        parameters=(
            ScientificParameter(name="source_current", value=source.current),
        ),
        models=(
            ModelReference("electrical.dc.ideal_current_source", "0.1.0"),
        ),
        required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    )
