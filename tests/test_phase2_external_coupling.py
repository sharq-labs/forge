"""Phase 2 BR12 -- external-participant infrastructure: labelled mocks, failure classes, interface contracts.

Every session in this file is a MOCK (``ExternalProviderIdentity(mock=True)``): it
returns fixed fields so the coupling mechanics can be exercised.  Nothing here is
evidence that any real external solver executes or couples.  The real FE/CFD
path is BLOCKED (policy) and its tests are NOT WRITTEN; see DEFERRED_VALIDATION.md.

This file also writes the end-to-end field-mapped coupled run through the
runtime's TransferEngine that Phase 1 left NOT WRITTEN (DV-34).

NOT RUN (Phase 2 build phase): docs/work/DEFERRED_VALIDATION.md, DV-60..DV-62.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.execution.multiphysics import AdvanceResult, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.authority import EXTERNAL_PROVIDER_COUPLING, CouplingMaturity
from engcore.execution.multiphysics.external import (
    ExternalProviderFailure, ExternalProviderIdentity, ExternalSolverParticipant,
)
from engcore.execution.multiphysics.interface_exchange import (
    ExchangeKind, InterfaceContract, InterfaceExchange, interface_flux_balance,
)
from engcore.execution.multiphysics.runtime import CouplingWindowNotConverged
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import (
    CouplingEdge, CouplingPlan, CouplingScheme, FieldAlgebra, FieldMappingDefinition, FieldMappingMethod,
    IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.scientific.fields.semantics import FieldSemantics, InterfaceConvention
from engcore.scientific.fields.interface_transfer import InterfaceTransfer
from engcore.scientific.semantics import QuantitySemantics, QuantityRole, ConservedQuantity
from engcore.system_runtime.authorities import MultiphysicsAuthority

UNKNOWN = Uncertainty.unknown("mock session: no uncertainty")
SOLID = StructuredMesh("solid", Quantity(1, "m"), Quantity(1, "m"), 3, 3)   # 2 x 2 cells
FLUID = StructuredMesh("fluid", Quantity(1, "m"), Quantity(1, "m"), 4, 4)   # 3 x 3 cells
TEMPERATURE = QuantitySemantics("fixture:temperature", "K", (QuantityRole.INTENSIVE,))
HEAT_FLUX = QuantitySemantics("fixture:heat_flux", "W/m**2", (QuantityRole.DENSITY, QuantityRole.FLOW))
SOLID_NORMAL = InterfaceConvention("solid", SOLID.fingerprint(), "fixture:world", 1, (0, 0, 1))
FLUID_NORMAL = InterfaceConvention("fluid", FLUID.fingerprint(), "fixture:world", 1, (0, 0, -1))
TRANSFER = InterfaceTransfer(SOLID_NORMAL, FLUID_NORMAL, HEAT_FLUX, ConservedQuantity("fixture:heat", "W"),
    "normal_density", "equal_and_opposite_outward", "full", "common_plane_rectangles",
    (0, 0, 0), (1, 0, 0), (0, 1, 0))
FLUX_S = FieldDefinition("q_solid", "W/m**2", "solid", FieldLocation.CELL,
    semantics=FieldSemantics("normal_flux", HEAT_FLUX, interface=SOLID_NORMAL))
FLUX_F = FieldDefinition("q_fluid", "W/m**2", "fluid", FieldLocation.CELL,
    semantics=FieldSemantics("normal_flux", HEAT_FLUX, interface=FLUID_NORMAL))
TEMP_F = FieldDefinition("t_fluid", "K", "fluid", FieldLocation.CELL, semantics=FieldSemantics("intensive", TEMPERATURE))
TEMP_S = FieldDefinition("t_solid", "K", "solid", FieldLocation.CELL, semantics=FieldSemantics("intensive", TEMPERATURE))


def _field_port(port_id, direction, definition, quantity):
    return PortDefinition(port_id, PortDirection(direction), PortKind.FIELD, quantity, definition.unit,
                          field=definition, algebra=FieldAlgebra.SCALAR, semantics=definition.semantics.quantity)


def _identity(pid):
    return ExternalProviderIdentity(pid, "0.0-mock", f"mock-{pid}", "1", mock=True)


class MockSession:
    """A labelled mock: it writes fixed fields; it is not a solver."""

    def __init__(self, pid, store, output, definition, mesh, values, *, fail_with=None):
        self.identity = _identity(pid)
        self.store, self.output, self.definition, self.mesh, self.values = store, output, definition, mesh, values
        self.fail_with = fail_with

    def _record(self):
        record, _ = FieldValue(self.definition, self.mesh, np.asarray(self.values, float)).store(self.store)
        return record

    def initialize(self, instant, inputs, uncertainty):
        return InitializationResult({self.output: self._record()}, {self.output: UNKNOWN})

    def advance(self, request):
        if self.fail_with is not None:
            raise self.fail_with
        return AdvanceResult(request.end, {self.output: self._record()}, {self.output: UNKNOWN}, 1, True)

    def snapshot(self, instant):  # pragma: no cover - explicit plan: never checkpointed
        raise AssertionError("not checkpointed")

    def restore(self, snapshot):  # pragma: no cover
        raise AssertionError("not restored")

    def finalize(self):
        pass


def _spec(pid, ports):
    identity = _identity(pid)
    return ParticipantSpec(pid, "mock-model", "1", "mock", "1", identity.provider_id, identity.provider_version,
                           identity.adapter_id, identity.adapter_version, tuple(ports), transient=True)


def _graph(flux_method=FieldMappingMethod.CONSERVATIVE_CELL):
    solid = _spec("solid", [_field_port("q", "output", FLUX_S, "heat_flux"), _field_port("t", "input", TEMP_S, "temperature")])
    fluid = _spec("fluid", [_field_port("q", "input", FLUX_F, "heat_flux"), _field_port("t", "output", TEMP_F, "temperature")])
    edges = (
        CouplingEdge("e_flux", PortRef("solid", "q"), PortRef("fluid", "q"),
                     mapping=FieldMappingDefinition("flux", flux_method),
                     interface_transfer=TRANSFER),
        CouplingEdge("e_temp", PortRef("fluid", "t"), PortRef("solid", "t"),
                     mapping=FieldMappingDefinition("temp", FieldMappingMethod.CONSERVATIVE_CELL)),
    )
    return PhysicsGraph("mock-interface", (solid, fluid), edges, supports=(SOLID, FLUID)), solid, fluid


CONTRACT = InterfaceContract("solid-fluid", (
    InterfaceExchange("e_flux", ExchangeKind.FLUX_DENSITY, "edge_interface_transfer"),
    InterfaceExchange("e_temp", ExchangeKind.INTENSIVE),
))


def _runtime(*, solid_fail=None):
    graph, solid, fluid = _graph()
    store = InMemoryBulkStore()
    participants = {
        "solid": ExternalSolverParticipant(solid, MockSession("solid", store, "q", FLUX_S, SOLID, np.full((2, 2), 100.0),
                                                              fail_with=solid_fail)),
        "fluid": ExternalSolverParticipant(fluid, MockSession("fluid", store, "t", TEMP_F, FLUID, np.full((3, 3), 310.0))),
    }
    plan = CouplingPlan("mock-interface", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("solid", "fluid"))
    return MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store)


# ---- an end-to-end field-mapped run (Phase 1 DV-34) ------------------------------------------------------------


def test_a_field_coupled_run_maps_the_flux_conservatively_and_records_it():
    run = _runtime().run("mock", external_inputs={})
    diagnostics = {d["edge_id"]: d["mapping"] for d in run.windows[0].iterations[-1].mapping_diagnostics}
    assert diagnostics["e_flux"]["provenance"]["method"] == "executed_common_plane_interface_overlap"
    assert diagnostics["e_temp"]["provenance"]["conservative"] is False
    assert diagnostics["e_flux"]["conservation_relative_error"] <= 1e-12
    balance = interface_flux_balance(run, CONTRACT)
    assert [b["status"] for b in balance] == ["transfer_integral_diagnostic"]
    assert balance[0]["coupled_physical_conservation"] == "unknown"
    assert "independent solver balance is not established" in balance[0]["notice"]
    assert diagnostics["e_flux"]["provenance"]["applied_sign"] == -1
    assert diagnostics["e_flux"]["provenance"]["target_total_normal_component"] == pytest.approx(-100.0)


# ---- the interface contract ---------------------------------------------------------------------------------------


def test_the_contract_is_honoured_by_a_conservative_flux_and_a_consistent_temperature():
    graph, _, _ = _graph()
    assert CONTRACT.problems(graph) == []


def test_a_flux_mapped_by_nearest_site_is_refused():
    with pytest.raises(InvalidScientificProblem, match="full-coverage"):
        _graph(flux_method=FieldMappingMethod.NEAREST)


def test_a_flux_without_a_sign_convention_is_refused():
    with pytest.raises(InvalidScientificProblem, match="sign convention"):
        InterfaceExchange("e_flux", ExchangeKind.FLUX_DENSITY)


def test_a_two_way_interface_needs_one_flux_and_one_intensive_quantity_back():
    graph, _, _ = _graph()
    flux_only = InterfaceContract("x", (InterfaceExchange("e_flux", ExchangeKind.FLUX_DENSITY, "edge_interface_transfer"),))
    assert any("exactly one flux" in p for p in flux_only.problems(graph))


# ---- mocks are labelled and not admitted as provider executions ---------------------------------------------


def _call():
    return SimpleNamespace(run_id="sys", node=SimpleNamespace(node_id="mock", commits_state=False))


def test_the_authority_refuses_mock_external_participants_unless_allowed():
    refused = MultiphysicsAuthority("mock-node", _runtime(), run_kwargs=lambda c: {"external_inputs": {}}, outputs={})
    outcome = refused.execute(_call())
    assert outcome.status == "failed" and "MOCK external participants" in outcome.reason
    allowed = MultiphysicsAuthority("mock-node", _runtime(), run_kwargs=lambda c: {"external_inputs": {}}, outputs={},
                                    allow_mock_participants=True)
    outcome = allowed.execute(_call())
    assert outcome.status == "succeeded" and outcome.diagnostics["mock_participants"] == "fluid,solid"
    assert refused.identity_digest != allowed.identity_digest


def test_a_real_identity_keeps_its_checkpoint_scope():
    real = ExternalProviderIdentity("fenicsx", "0.9", "forge_fenicsx", "1")
    assert "mock" not in real.state_scope and "mock" in _identity("x").state_scope


# ---- failure classification ------------------------------------------------------------------------------------


def test_a_crashed_provider_is_a_classified_refusal_not_a_numerical_failure():
    with pytest.raises(ExternalProviderFailure, match="failed during advance") as caught:
        _runtime(solid_fail=OSError("solver process exited 139")).run("crash", external_inputs={})
    assert caught.value.phase == "advance" and caught.value.identity.mock


def test_a_numerical_non_convergence_keeps_its_retryable_type():
    with pytest.raises(CouplingWindowNotConverged):
        _runtime(solid_fail=CouplingWindowNotConverged("internal solve did not converge")).run("nc", external_inputs={})


# ---- maturity is stated per claim ---------------------------------------------------------------------------------


def test_no_provider_claims_an_end_to_end_coupling_it_has_not_executed():
    by_id = {m.provider_id: m for m in EXTERNAL_PROVIDER_COUPLING}
    assert by_id["openfoam"].coupled_execution is CouplingMaturity.NOT_IMPLEMENTED
    assert by_id["fe_cfd_conjugate_heat_transfer"].coupled_execution is CouplingMaturity.BLOCKED
    assert all(m.coupled_execution is not CouplingMaturity.IMPLEMENTED_UNEXECUTED or m.basis for m in by_id.values())
