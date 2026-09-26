"""BIG 13 generalizations of the BIG 12 runtime, each minimal and each with the adversarial case that justifies it.

* ``NodeCall.execution_identity`` - an authority can bind side data (a field held in a bulk store) to EXACTLY its own execution; a consumer
  sees the same value as ``InputValue.producer_identity``.  A field for another execution is therefore not found, never substituted.
* ``MultiphysicsAuthority(extractors=, artifacts=)`` - scalars derived from the coupled run's own histories are node outputs whose uncertainty
  stays UNKNOWN, and bulk artifacts are referenced by digest.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, ArtifactRef, CallbackAuthority, ExecutionProfile, MultiphysicsAuthority, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeStatus,
    OutputValue, RequestedObservable, RunStatus, SystemExecutor,
)
from engcore.scientific.results.uncertainty import UncertaintyKind
from tests.system_runtime_fixtures import UNKNOWN, build, sha
from tests.test_system_runtime_review_fixes import _coupled_stub


def test_a_node_sees_its_own_execution_identity_and_the_consumer_sees_the_same_value_as_the_producer_identity():
    request, context, knobs = build()
    seen = {}
    held = {}
    heat = context.authorities._items["heat-auth"]
    original = heat._fn

    def heat_fn(call):
        seen["producer"] = call.execution_identity
        held[call.execution_identity] = "field-A"                       # side data keyed by this exact execution
        return original(call)

    heat._fn = heat_fn
    thermal = context.authorities._items["thermal-auth"]
    orig_t = thermal._fn

    def thermal_fn(call):
        seen["consumer_view"] = call.inputs["heat_in"].producer_identity
        seen["lookup"] = held.get(call.inputs["heat_in"].producer_identity)
        return orig_t(call)

    thermal._fn = thermal_fn
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED
    assert seen["producer"] and seen["producer"] == seen["consumer_view"] == result.receipt("heat").execution_identity_digest
    assert seen["lookup"] == "field-A"


def test_multiphysics_extractors_are_node_outputs_with_unknown_uncertainty_and_artifacts_are_referenced_by_digest():
    request, context, knobs = build()
    payload = b"t_s,T_K\n0,300\n1800,305\n"
    run_holder = {}

    def artifacts(run, call):
        run_holder["seen"] = run.run_id
        return (ArtifactRef("history.csv", "timeseries_csv", hashlib.sha256(payload).hexdigest(), "presentation, not evidence"),)

    auth = MultiphysicsAuthority("stub-coupled-extract", _coupled_stub(UNKNOWN), run_kwargs=lambda c: {}, outputs={}, state_owners={},
                                 extractors={"peak_temperature": lambda run, call: Quantity(305.0, "K"), "mean_of_two": lambda run, call: Quantity(302.5, "K")},
                                 artifacts=artifacts, applicability=lambda run, call: (ApplicabilityReport("ok", "within", sha("e")),))
    context.authorities.register(auth)
    node = NodeSpec("stub", NodeKind.MULTIPHYSICS_EXECUTION, auth.ref, (NodeOutputSpec("peak_temperature", "K"), NodeOutputSpec("mean_of_two", "K")), applicability_checks=("ok",))
    request = replace(request, nodes=(node,), observables=(RequestedObservable("peak", "stub", "peak_temperature", "K"),), constraint_observations=(),
                      profile=ExecutionProfile(("multiphysics",)))
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    out = result.node_outputs["stub"]["peak_temperature"]
    assert out.value.magnitude == 305.0 and out.uncertainty.kind is UncertaintyKind.UNKNOWN            # derived from histories: never a quantified error bar
    (art,) = result.receipt("stub").artifacts
    assert art.name == "history.csv" and art.digest == hashlib.sha256(payload).hexdigest() and run_holder["seen"].endswith("stub")


def test_an_extractor_that_raises_fails_the_node_and_exposes_nothing():
    request, context, knobs = build()

    def boom(run, call):
        raise ValueError("the history has no discharge window")

    auth = MultiphysicsAuthority("stub-coupled-boom", _coupled_stub(UNKNOWN), run_kwargs=lambda c: {}, outputs={}, state_owners={}, extractors={"peak": boom},
                                 applicability=lambda run, call: (ApplicabilityReport("ok", "within", sha("e")),))
    context.authorities.register(auth)
    node = NodeSpec("stub", NodeKind.MULTIPHYSICS_EXECUTION, auth.ref, (NodeOutputSpec("peak", "K"),), applicability_checks=("ok",))
    request = replace(request, nodes=(node,), observables=(RequestedObservable("peak", "stub", "peak", "K"),), constraint_observations=(), profile=ExecutionProfile(("multiphysics",)))
    result = SystemExecutor(context).run(request)
    assert result.receipt("stub").status is NodeStatus.FAILED and "no discharge window" in result.receipt("stub").reason
    assert result.node_outputs.get("stub") is None and result.observable("peak").value is None


def test_the_authority_identity_covers_the_extractor_names_and_the_artifact_hook():
    _, context, _ = build()
    a = MultiphysicsAuthority("stub-a", _coupled_stub(UNKNOWN), run_kwargs=lambda c: {}, outputs={}, extractors={"x": lambda r, c: Quantity(1.0, "K")})
    b = MultiphysicsAuthority("stub-a", _coupled_stub(UNKNOWN), run_kwargs=lambda c: {}, outputs={}, extractors={"y": lambda r, c: Quantity(1.0, "K")})
    c = MultiphysicsAuthority("stub-a", _coupled_stub(UNKNOWN), run_kwargs=lambda c: {}, outputs={}, extractors={"x": lambda r, c: Quantity(1.0, "K")}, artifacts=lambda r, c: ())
    assert len({a.identity_digest, b.identity_digest, c.identity_digest}) == 3
