"""Support gates for the DC adapters must honour model VERSION and every named model.

Two defects these tests pin:

1. The ngspice adapter declared ``served_models = ()`` and matched realizations
   by model id alone, so a problem naming ``electrical.dc.kcl@99.0`` was
   accepted and bound to the code for ``@0.1.0``. The native solver refused the
   same problem. The two adapters disagreed about what they support.

2. The core's served-model check passes when the problem names *one* served
   model. A problem naming a served model plus an unknown one was accepted, the
   unknown model was never assessed, and the result (whose ``models`` come from
   the circuit) did not show it.

The second is enforced in the DC adapter's ``additional_support_gap`` hook, not
in the core: ``scientific/solvers/protocol.py`` is pinned by the core
certificate and changing it is a recertification decision.

A gate on ``support_gap`` alone is not enough: the execution entry points must
refuse too. ``verify_problem_matches_circuit`` requires the problem to name
exactly the circuit's models, and both ``prepare`` methods check support.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from engcore.domains.electrical.dc.errors import (
    CircuitBindingError,
    ElectricalDCError,
)
from engcore.domains.electrical.dc.problem import (
    build_dc_problem,
    verify_problem_matches_circuit,
)
from engcore.domains.electrical.dc.solver import ElectricalDCSolver, solve_circuit
from engcore.domains.electrical.dc_realizations import realizations_for_models
from engcore.domains.electrical.ngspice import (
    NgspiceDCSolver,
    solve_circuit_with_ngspice,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity


def _divider_circuit():
    return DCCircuit(
        circuit_id="gate",
        nodes=(
            ElectricalNode("n0"),
            ElectricalNode("n1"),
            ElectricalNode("gnd", is_reference=True),
        ),
        resistors=(
            Resistor("R1", "n0", "n1", Quantity(1000.0, "ohm")),
            Resistor("R2", "n1", "gnd", Quantity(1000.0, "ohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "n0", "gnd", Quantity(1.0, "volt")),
        ),
    )


def _divider_problem():
    return build_dc_problem(_divider_circuit())


def _with_models(problem, models):
    return dataclasses.replace(problem, models=tuple(models))


def test_a_genuine_problem_is_supported_by_both_adapters():
    problem = _divider_problem()

    assert ElectricalDCSolver().support_gap(problem) == ()
    assert NgspiceDCSolver().support_gap(problem) == ()


def test_ngspice_refuses_a_model_version_it_does_not_realize():
    problem = _divider_problem()
    forged = _with_models(
        problem, (ModelReference(m.model_id, "99.0") for m in problem.models)
    )

    assert NgspiceDCSolver().support_gap(forged)


def test_native_and_ngspice_agree_on_a_forged_model_version():
    problem = _divider_problem()
    forged = _with_models(
        problem, (ModelReference(m.model_id, "99.0") for m in problem.models)
    )

    assert ElectricalDCSolver().support_gap(forged)
    assert NgspiceDCSolver().support_gap(forged)


def test_native_refuses_a_problem_naming_an_unserved_model_alongside_served_ones():
    problem = _divider_problem()
    mixed = _with_models(
        problem,
        (*problem.models, ModelReference("thermal.made_up_model", "1.0")),
    )

    gap = ElectricalDCSolver().support_gap(mixed)
    assert gap
    assert any("made_up_model" in reason for reason in gap)


def test_ngspice_refuses_a_problem_naming_an_unrealized_model_alongside_realized_ones():
    problem = _divider_problem()
    mixed = _with_models(
        problem,
        (*problem.models, ModelReference("thermal.made_up_model", "1.0")),
    )

    assert NgspiceDCSolver().support_gap(mixed)


def test_realization_lookup_requires_the_exact_version():
    problem = _divider_problem()
    kcl = problem.models[0]

    assert len(realizations_for_models([kcl])) == 1
    assert realizations_for_models([ModelReference(kcl.model_id, "99.0")]) == ()


# -- execution paths ----------------------------------------------------------


def _forged_version(problem):
    return _with_models(
        problem, (ModelReference(m.model_id, "99.0") for m in problem.models)
    )


def _extra_model(problem):
    return _with_models(
        problem,
        (*problem.models, ModelReference("thermal.made_up_model", "1.0")),
    )


def _missing_model(problem):
    return _with_models(problem, problem.models[:1])


TAMPERED = pytest.mark.parametrize(
    "tamper",
    [_forged_version, _extra_model, _missing_model],
    ids=["forged-version", "extra-model", "missing-model"],
)


def test_the_genuine_problem_matches_its_circuit():
    verify_problem_matches_circuit(_divider_problem(), _divider_circuit())


@TAMPERED
def test_the_binding_check_refuses_a_problem_whose_models_are_not_the_circuits(
    tamper,
):
    circuit = _divider_circuit()
    with pytest.raises(CircuitBindingError):
        verify_problem_matches_circuit(tamper(build_dc_problem(circuit)), circuit)


@TAMPERED
def test_native_solve_refuses_a_tampered_problem(tamper):
    circuit = _divider_circuit()
    with pytest.raises(CircuitBindingError):
        solve_circuit(circuit, run_id="gate", problem=tamper(build_dc_problem(circuit)))


@TAMPERED
def test_ngspice_solve_refuses_a_tampered_problem_before_running_the_provider(
    tamper,
):
    # No ngspice is needed: the refusal comes before the provider is invoked.
    circuit = _divider_circuit()
    with pytest.raises(CircuitBindingError):
        solve_circuit_with_ngspice(
            circuit, run_id="gate", problem=tamper(build_dc_problem(circuit))
        )


@pytest.mark.parametrize("tamper", [_forged_version, _extra_model])
def test_both_prepare_methods_refuse_an_unsupported_problem(tamper):
    circuit = _divider_circuit()
    problem = tamper(build_dc_problem(circuit))

    native = ElectricalDCSolver()
    native.bind_circuit(circuit, problem.problem_id)
    with pytest.raises(ElectricalDCError):
        native.prepare(problem)

    external = NgspiceDCSolver()
    external.bind_circuit(circuit, problem.problem_id)
    with pytest.raises(InvalidScientificProblem):
        external.prepare(problem)
