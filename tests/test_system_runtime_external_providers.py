"""A coupled system-runtime node may not run external providers it does not report (ERT V1, Big Rock 14).

The executor already refuses a node that names provider bindings but reports
no execution.  A coupled node can run external providers through
``ExternalSolverParticipant``s without naming any binding; ``MultiphysicsAuthority``
now fails such a node unless every admitted provider identity appears among
its reported provider records.  Nothing is derived.  The sessions here are
in-process MOCKS: no external program runs.  NOT YET EXECUTED (build phase):
see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.external import ExternalProviderIdentity, ExternalSnapshot, ExternalSolverParticipant
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime.authorities import MultiphysicsAuthority
from engcore.system_runtime.records import ProviderRecordRef

UNKNOWN = Uncertainty.unknown("mock provider output uncertainty not quantified")


class Session:
    snapshot_integrity_codec = ("mock.inline-ascii-step-count", "1")

    def snapshot_integrity_bytes(self, snapshot):
        return snapshot.token

    def __init__(self, out, inp, fn, version="1.0"):
        self._identity = ExternalProviderIdentity("thermo", version, "thermo-adapter", "1")
        self.out, self.inp, self.fn, self.steps = out, inp, fn, 0

    @property
    def identity(self):
        return self._identity

    def initialize(self, _t, _i, _u):
        return InitializationResult({self.out: Quantity(0, "K")}, {self.out: UNKNOWN})

    def advance(self, request):
        self.steps += 1
        return AdvanceResult(request.end, {self.out: self.fn(request.inputs[self.inp])}, {self.out: UNKNOWN}, 1, True)

    def snapshot(self, _t):
        return ExternalSnapshot(hashlib.sha256(str(self.steps).encode()).hexdigest(), f"s{self.steps}", str(self.steps).encode("ascii"))

    def restore(self, snapshot):
        self.steps = int(snapshot.token)

    def finalize(self):
        pass


def _spec(pid, out, inp, version="1.0"):
    return ParticipantSpec(pid, "m", "1", "r", "1", "thermo", version, "thermo-adapter", "1",
                           (PortDefinition(inp, PortDirection.INPUT, PortKind.SCALAR, "temperature", "K"),
                            PortDefinition(out, PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")),
                           transient=True, checkpointable=True, deterministic_restore=True)


def _runtime():
    """x = y/2 + 5, y = x, both participants external (mock) providers thermo@1.0; converges to 10 K."""
    a = ExternalSolverParticipant(_spec("a", "x", "y"), Session("x", "y", lambda y: Quantity(y.magnitude_in("K") / 2 + 5, "K")))
    b = ExternalSolverParticipant(_spec("b", "y", "x"), Session("y", "x", lambda x: Quantity(x.magnitude_in("K"), "K")))
    graph = PhysicsGraph("ext-node", (a.spec, b.spec), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                                        CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("ext-node", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_y", 0.0, Quantity(1e-6, "K"))),
                        max_iterations=200)
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"a": a, "b": b}, resolver=BulkDataResolver(store), store=store)


def _record(provider_id="thermo", version="1.0"):
    return ProviderRecordRef(provider_id, version, "", "a" * 64, "", True)


def _authority(providers=None):
    initial = {"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")}
    return MultiphysicsAuthority(
        "ext-node", _runtime(),
        run_kwargs=lambda call: {"external_inputs": {}, "initial_coupling_values": initial,
                                 "initial_coupling_uncertainty": {k: UNKNOWN for k in initial}},
        outputs={"x": "a.x"}, providers=providers)


def _call():
    return SimpleNamespace(run_id="sys", node=SimpleNamespace(node_id="coupled", commits_state=False))


def test_external_providers_without_reported_executions_fail_the_node():
    outcome = _authority().execute(_call())
    assert outcome.status == "failed" and "untraceable" in outcome.reason
    assert "thermo@1.0" in outcome.reason


def test_reported_records_must_name_the_admitted_provider_version():
    outcome = _authority(providers=lambda run: (_record(version="2.0"),)).execute(_call())
    assert outcome.status == "failed" and "untraceable" in outcome.reason


def test_a_node_reporting_its_external_provider_succeeds_and_carries_the_record():
    outcome = _authority(providers=lambda run: (_record(),)).execute(_call())
    assert outcome.status == "succeeded", outcome.reason
    assert [(r.provider_id, r.provider_version) for r in outcome.provider_records] == [("thermo", "1.0")]
