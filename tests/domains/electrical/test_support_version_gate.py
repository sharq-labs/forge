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
"""

from __future__ import annotations

import dataclasses

from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from engcore.domains.electrical.dc.problem import build_dc_problem
from engcore.domains.electrical.dc.solver import ElectricalDCSolver
from engcore.domains.electrical.dc_realizations import realizations_for_models
from engcore.domains.electrical.ngspice import NgspiceDCSolver
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity


def _divider_problem():
    circuit = DCCircuit(
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
    return build_dc_problem(circuit)


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
