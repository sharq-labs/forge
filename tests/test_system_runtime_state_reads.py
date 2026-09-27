"""BIG 12 R2 / (d)-2 and (b), closed in BIG 14 14.1.

R2 / (d)-2: a node's state reads were not DAG edges.  A node sees only the owners it declares it reads (``reads_owners``) or writes; the
planner orders it against every writer of them; an UNKNOWN value in a visible owner is an UNKNOWN input.  (b): executed nodes that
declared neither an applicability check nor a waiver are named in the credibility notes (derived from the plan; nothing stored moves).
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    CallbackAuthority, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeStatus, OutputValue, OwnerState, PreflightStatus,
    compile_plan, preflight, trust_handoff, SystemExecutor,
)
from engcore.system_runtime.plan import PlanNode
from engcore.system_runtime.request import NodeSpec as _NodeSpec
from tests.system_runtime_fixtures import UNKNOWN, build, sha
from tests.test_system_runtime_review_fixes import _state_commit_request

KNOWN = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.5, "K"), source="declared", method="declared")


def _reader(request, context, *, reads=("cell",), depends=("thermal",), uncertainty=UNKNOWN, accounts=False, node_id="probe"):
    seen = {}

    def fn(call):
        seen["t"] = call.state.owner("cell").values[0].value
        return NodeOutcome("succeeded", {"t": OutputValue(seen["t"], uncertainty, "probe")})

    auth = CallbackAuthority(f"{node_id}-auth", fn, config={"accounts": accounts}, deterministic=True)
    auth.accounts_for_input_uncertainty = accounts
    context.authorities.register(auth)
    node = NodeSpec(node_id, NodeKind.AGGREGATE, auth.ref, (NodeOutputSpec("t", "K"),), depends_on=depends, reads_owners=reads)
    return replace(request, nodes=request.nodes + (node,)), seen


def test_a_reader_unordered_against_a_writer_of_its_owner_is_refused_by_the_planner():
    request, context, _ = build()
    unordered, _ = _reader(request, context, depends=())
    with pytest.raises(InvalidScientificProblem, match="no dependency path"):
        compile_plan(unordered)
    request, context, _ = build()
    ordered, seen = _reader(request, context)
    result = SystemExecutor(context).run(ordered)
    assert result.receipt("probe").status is NodeStatus.SUCCEEDED
    assert seen["t"] == result.final_state.owner("cell").values[0].value          # it read the state AFTER the writer it depends on


def test_two_writers_of_one_owner_must_be_ordered():
    request, context, _ = build()
    thermal = next(n for n in request.nodes if n.node_id == "thermal")
    twin = replace(thermal, node_id="thermal_b", inputs=(NodeInput("heat_in", "heat", "power", "W"),), material_refs=(), environment_requirements=())
    with pytest.raises(InvalidScientificProblem, match="no dependency path"):
        compile_plan(replace(request, nodes=request.nodes + (twin,)))


def test_an_undeclared_state_read_is_refused_not_served():
    request, context, _ = build()
    blind, _ = _reader(request, context, reads=())
    result = SystemExecutor(context).run(blind)
    receipt = result.receipt("probe")
    assert receipt.status is NodeStatus.FAILED and "not declared as read or written" in receipt.reason


def test_a_quantified_output_from_an_unknown_state_read_is_refused_unless_the_authority_accounts_for_it():
    """The review's R2 bypass: a non-committing node re-quantified an UNKNOWN state value."""
    request, context, _ = build()
    claims, _ = _reader(request, context, uncertainty=KNOWN)
    receipt = SystemExecutor(context).run(claims).receipt("probe")
    assert receipt.status is NodeStatus.FAILED and "state" in receipt.reason and "UNKNOWN" in receipt.reason
    request, context, _ = build()
    accounted, _ = _reader(request, context, uncertainty=KNOWN, accounts=True)
    assert SystemExecutor(context).run(accounted).receipt("probe").status is NodeStatus.SUCCEEDED


def test_a_committing_node_cannot_requantify_one_variable_while_another_visible_variable_is_unknown():
    """The review's second R2 variant: the solve also depends on an UNKNOWN value it reads (here in a second visible owner); re-quantifying
    the written temperature is refused, and it commits when nothing it sees is UNKNOWN."""
    request, context = _state_commit_request(KNOWN, KNOWN)
    reads_soc = replace(request.nodes[0], reads_owners=("cooler",))
    for soc_uncertainty, expected in ((UNKNOWN, NodeStatus.FAILED), (KNOWN, NodeStatus.SUCCEEDED)):
        cooler = OwnerState("cooler", "component", (InitialStateValue("soc", Quantity(0.8, "dimensionless"),
                                                                      soc_uncertainty if soc_uncertainty is UNKNOWN else Uncertainty(
                                                                          kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, "dimensionless"),
                                                                          source="declared", method="declared")),))
        run = replace(request, nodes=(reads_soc,), initial_state=replace(request.initial_state, owners=request.initial_state.owners + (cooler,)))
        receipt = SystemExecutor(context).run(run).receipt("stub")
        assert receipt.status is expected, receipt.reason
        assert expected is NodeStatus.SUCCEEDED or "cooler.soc" in receipt.reason


def test_a_multiphysics_authority_mapping_an_undeclared_owner_is_refused_in_preflight():
    request, context = _state_commit_request(UNKNOWN, UNKNOWN)
    node = request.nodes[0]
    reader = replace(node, commits_state=False, writes_owners=(), applicability_checks=())
    request = replace(request, nodes=(reader,))
    report = preflight(request, compile_plan(request), context)
    assert report.status is PreflightStatus.REFUSED and "UNDECLARED_STATE_READ" in report.codes()
    declared = replace(request, nodes=(replace(reader, reads_owners=("cell",)),))
    assert "UNDECLARED_STATE_READ" not in preflight(declared, compile_plan(declared), context).codes()


def test_reads_owners_is_serialized_only_when_declared_so_stored_digests_do_not_move():
    request, context, _ = build()
    plain = request.nodes[0]
    assert "reads_owners" not in plain.to_dict() and _NodeSpec.from_dict(plain.to_dict()) == plain
    reading = replace(plain, reads_owners=("cell",))
    assert reading.to_dict()["reads_owners"] == ["cell"] and _NodeSpec.from_dict(reading.to_dict()) == reading
    with pytest.raises(InvalidScientificProblem, match="omission"):
        _NodeSpec.from_dict({**plain.to_dict(), "reads_owners": []})
    plan = compile_plan(replace(request, nodes=tuple(reading if n.node_id == plain.node_id else n for n in request.nodes)))
    node = next(n for n in plan.nodes if n.node_id == plain.node_id)
    assert PlanNode.from_dict(json.loads(json.dumps(node.to_dict()))) == node
    with pytest.raises(InvalidScientificProblem, match="read and written"):
        replace(plain, commits_state=True, writes_owners=("cell",), reads_owners=("cell",), applicability_waiver="w")


def test_b_nodes_that_declare_neither_an_applicability_check_nor_a_waiver_are_named_in_the_credibility_notes():
    from engcore.system_runtime.assess import undeclared_applicability
    request, context, _ = build()
    result = SystemExecutor(context).run(request)
    assert undeclared_applicability(result) == ("heat", "report")                    # thermal declares a check; derived nodes are not listed
    notes = trust_handoff(result, request).notes
    assert "NEITHER an applicability check NOR a waiver" in notes and "heat, report" in notes


def test_two_committing_nodes_of_different_owners_must_still_be_ordered_because_they_share_the_state_clock():
    """Review of this batch M1: unordered committers of different owners saw the clock of whichever commit the tie-break ran first."""
    from engcore.system_runtime import LiteralInput
    request, context, _ = build()
    thermal = next(n for n in request.nodes if n.node_id == "thermal")
    other = replace(thermal, node_id="cooler_step", inputs=(NodeInput("heat_in", "heat", "power", "W"),), material_refs=(), environment_requirements=(),
                    literals=(LiteralInput("ambient", Quantity(293.15, "K"), UNKNOWN),), writes_owners=("cooler",))
    initial = replace(request.initial_state, owners=request.initial_state.owners + (
        OwnerState("cooler", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN),)),))
    with pytest.raises(InvalidScientificProblem, match="state-committing nodes"):
        compile_plan(replace(request, nodes=request.nodes + (other,), initial_state=initial))
    compile_plan(replace(request, nodes=request.nodes + (replace(other, depends_on=("thermal",)),), initial_state=initial))


def test_the_view_filters_owners_and_shows_the_clock_to_committing_nodes_only():
    from engcore.system_runtime import SystemState
    from engcore.system_runtime.state import StateView
    request, _, _ = build()
    extra = OwnerState("cooler", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN),))
    spec = replace(request.initial_state, owners=request.initial_state.owners + (extra,))
    state = SystemState.initial(spec, request_digest=request.digest, system_digest=request.system.digest, environment_digest=request.environment.digest)
    reader = StateView(state, ("cell",))
    assert [o.owner_id for o in reader.owners] == ["cell"] and reader.request_digest == request.digest
    for hidden in ("time", "seconds", "sequence", "digest", "previous_digest", "produced_by"):
        with pytest.raises(AttributeError):
            getattr(reader, hidden)
    assert all(owner == "cell" for owner, _ in reader.material_state_digests)
    committer = StateView(state, ("cell",), clock=True)
    assert committer.time == state.time
    with pytest.raises(AttributeError):
        committer.digest


def test_a_read_owner_that_the_initial_state_does_not_declare_is_refused_in_preflight():
    request, context, _ = build()
    typo, _ = _reader(request, context, reads=("cel",))
    assert "UNKNOWN_STATE_OWNER" in preflight(typo, compile_plan(typo), context).codes()


def test_the_view_hides_the_material_digests_and_provider_checkpoints_of_owners_it_does_not_see():
    """Focused re-review L3: filters that had no direct test."""
    from engcore.system_runtime import SystemState
    from engcore.system_runtime.state import ProviderCheckpointRef, StateView
    request, _, _ = build()
    extra = OwnerState("cooler", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN),))
    spec = replace(request.initial_state, owners=request.initial_state.owners + (extra,),
                   material_state_digests=request.initial_state.material_state_digests + (("cooler", sha("cooler-material")),))
    s0 = SystemState.initial(spec, request_digest=request.digest, system_digest=request.system.digest, environment_digest=request.environment.digest)
    s1 = s0.advance(time=Quantity(10, "s"), updates=(), produced_by="x",
                    provider_checkpoints=(ProviderCheckpointRef("cooler", sha("cp-cooler"), True), ProviderCheckpointRef("cell", sha("cp-cell"), True)))
    view = StateView(s1, ("cell",))
    assert {o for o, _ in view.material_state_digests} == {"cell"}
    assert [c.owner_id for c in view.provider_checkpoints] == ["cell"]


def test_a_committer_cannot_touch_the_provider_checkpoints_of_an_owner_it_does_not_write():
    """Focused re-review M: a committer replaced the whole checkpoint tuple, including owners it does not write."""
    from engcore.system_runtime import StateProposal
    from engcore.system_runtime.state import ProviderCheckpointRef
    request, context, knobs = build()
    thermal = next(n for n in request.nodes if n.node_id == "thermal")
    auth = context.authorities.resolve(thermal.authority)
    original = auth.execute

    def meddling(call):
        outcome = original(call)
        proposal = StateProposal(outcome.state_proposal.time, outcome.state_proposal.updates,
                                 (ProviderCheckpointRef("cooler", sha("forged"), True),))
        return replace(outcome, state_proposal=proposal)
    auth.execute = meddling
    receipt = SystemExecutor(context).run(request).receipt("thermal")
    assert receipt.status is NodeStatus.FAILED and "does not write" in receipt.reason
