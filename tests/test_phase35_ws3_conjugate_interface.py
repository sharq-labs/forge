"""Phase 3.5 WS3 -- conjugate heat-transfer interface admission and provider-pair maturity (infrastructure only).

No FE or CFD solver runs here and none is implemented: the real FEniCSx <-> OpenFOAM coupling is
BLOCKED by policy (OD-P2-1).  These tests check that a coupling graph expresses the two interface
conditions in the right form, and that the maturity record cannot claim execution, verification or
validation without recorded evidence.

NOT RUN (Phase 3.5 build phase): docs/work/DEFERRED_VALIDATION.md, DV-91.
"""

from __future__ import annotations

import pytest
from dataclasses import replace
from tests.test_phase2_external_coupling import (
    SOLID, FLUID, TEMPERATURE, HEAT_FLUX, TRANSFER, FLUX_S, FLUX_F, TEMP_S, TEMP_F,
)

from engcore.execution.multiphysics.conjugate_interface import (
    CHT_FENICSX_OPENFOAM, ConjugateHeatTransferInterface, PairStage, ProviderPairMaturity, StageStatus,
    admit_conjugate_interface,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, FieldAlgebra, FieldMappingDefinition,
    FieldMappingMethod, IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind,
    PortRef, TimePolicy,
)
from engcore.scientific.units.quantity import Quantity

def _port(pid, direction, unit, mesh, quantity):
    base = {("q", "solid"): FLUX_S, ("q", "fluid"): FLUX_F,
            ("t", "solid"): TEMP_S, ("t", "fluid"): TEMP_F}[(pid, mesh)]
    definition = replace(base, unit=unit)
    return PortDefinition(pid, PortDirection(direction), PortKind.FIELD, quantity, unit, field=definition,
                          algebra=FieldAlgebra.SCALAR, semantics=definition.semantics.quantity)


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _graph(*, flux_unit="W/m**2", flux_method=FieldMappingMethod.CONSERVATIVE_CELL, temp_unit="K"):
    solid = _spec("solid", [_port("q", "output", flux_unit, "solid", "heat_flux"), _port("t", "input", temp_unit, "solid", "temperature")])
    fluid = _spec("fluid", [_port("q", "input", flux_unit, "fluid", "heat_flux"), _port("t", "output", temp_unit, "fluid", "temperature")])
    flux = CouplingEdge("e_flux", PortRef("solid", "q"), PortRef("fluid", "q"), mapping=FieldMappingDefinition("flux", flux_method),
                        interface_transfer=TRANSFER)
    temp = CouplingEdge("e_temp", PortRef("fluid", "t"), PortRef("solid", "t"),
                        mapping=FieldMappingDefinition("temp", FieldMappingMethod.CONSERVATIVE_CELL))
    return PhysicsGraph("cht", (solid, fluid), (flux, temp), supports=(SOLID, FLUID))


def _plan(scheme=CouplingScheme.IMPLICIT, criteria=("e_flux", "e_temp")):
    time = TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s"))
    units = {"e_flux": "W/m**2", "e_temp": "K"}
    made = tuple(ConvergenceCriterion(e, 0.0, Quantity(1e-6, units[e])) for e in criteria)
    if scheme is CouplingScheme.EXPLICIT:
        return CouplingPlan("cht", scheme, IterationSemantics.SERIAL, time, ("solid", "fluid"))
    return CouplingPlan("cht", scheme, IterationSemantics.JACOBI, time, ("solid", "fluid"), made, max_iterations=20)


def _interface(normal="outward_normal_of:solid", **kw):
    base = dict(interface_id="gamma", solid="solid", fluid="fluid", temperature_edge="e_temp", heat_flux_edge="e_flux",
                flux_normal=normal)
    return ConjugateHeatTransferInterface(**{**base, **kw})


def _admit(interface, graph, plan):
    return admit_conjugate_interface(interface, graph, plan,
        temperature_semantics=TEMPERATURE, heat_flux_semantics=HEAT_FLUX)


def test_an_honest_graph_is_admitted_and_states_both_conditions_and_what_it_does_not_establish():
    admission = _admit(_interface(), _graph(), _plan())
    record = admission.to_dict()
    assert admission.dirichlet_receiver == "solid" and admission.neumann_receiver == "fluid"
    # the flux is stated along the SOURCE's (solid's) outward normal: heat leaving the solid enters the fluid
    assert admission.receiver_flux_sign == -1
    assert "validation" in record["does_not_establish"] and "stability" in " ".join(record["does_not_establish"])


def test_legacy_receiver_normal_cannot_override_the_executed_sign():
    with pytest.raises(InvalidScientificProblem, match="source-normal migration"):
        _admit(_interface("outward_normal_of:fluid"), _graph(), _plan())


@pytest.mark.parametrize("normal", ["outward normal of the solid", "outward_normal_of:wall", ""])
def test_a_flux_without_an_explicit_participant_normal_is_refused(normal):
    with pytest.raises(InvalidScientificProblem):
        _interface(normal)


@pytest.mark.parametrize("graph,match", [
    (lambda: _graph(flux_method=FieldMappingMethod.NEAREST), "full-coverage"),
    (lambda: _graph(flux_unit="W"), "dimension"),
    # a power-like "temperature" field is refused while the graph is built (it must be
    # transported whole), before the interface admission can name the missing temperature
    # dimension; either refusal keeps the wrong semantics out
    (lambda: _graph(temp_unit="W/m**2", flux_unit="W/m**2"), "dimension"),
])
def test_wrong_interface_semantics_are_refused(graph, match):
    with pytest.raises(InvalidScientificProblem, match=match):
        _admit(_interface(), graph(), _plan())


def test_an_implicit_plan_must_measure_both_interface_edges():
    with pytest.raises(InvalidScientificProblem, match="must monitor edges"):
        _admit(_interface(), _graph(), _plan(criteria=("e_temp",)))


def test_an_explicit_plan_admission_does_not_establish_physical_conditions():
    record = _admit(_interface(), _graph(), _plan(CouplingScheme.EXPLICIT)).to_dict()
    assert record["execution"]["coupled_physical_conservation"] == "unknown"
    assert record["execution"]["numerical_solution_verification"] == "not established"
    assert record["execution"]["implicit"] is False


def test_the_cht_pair_claims_nothing_it_has_not_shown():
    record = CHT_FENICSX_OPENFOAM.to_dict()
    assert not any(stage["reached"] for stage in record["stages"].values())
    assert "BLOCKED" in record["policy"]


def test_evidence_stages_need_a_recorded_run_and_every_earlier_stage():
    stages = {s: StageStatus(False, "x") for s in PairStage}
    with pytest.raises(InvalidScientificProblem, match="sha256"):
        ProviderPairMaturity("p", {**stages, PairStage.REAL_EXECUTION_DEMONSTRATED: StageStatus(True, "said so")}, "x")
    with pytest.raises(InvalidScientificProblem, match="cannot be reached before"):
        ProviderPairMaturity("p", {**stages, PairStage.NUMERICALLY_VERIFIED: StageStatus(True, "run", "a" * 64)}, "x")
    # validation with the first four stages reached but neither execution nor verification shown: still refused
    four = {s: StageStatus(s in list(PairStage)[:4], "x") for s in PairStage}
    with pytest.raises(InvalidScientificProblem, match="real_execution_demonstrated"):
        ProviderPairMaturity("p", {**four, PairStage.SCIENTIFICALLY_VALIDATED: StageStatus(True, "said so", "a" * 64)}, "x")
    assert CHT_FENICSX_OPENFOAM.to_dict()["evidence_ref_status"] == "asserted_not_resolved"
    with pytest.raises(InvalidScientificProblem, match="every stage"):
        ProviderPairMaturity("p", {PairStage.ADAPTER_IMPLEMENTED: StageStatus(True, "x")}, "x")
