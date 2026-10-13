"""F5 (hostile review, HIGH): a declared conservation failure in one window survives every later window.

The reproduced defect: ``MultiphysicsRuntime.run`` kept only the LAST window's
conservation audit, so a balance that failed in window 0 and closed in window 1
reported only the pass. These tests run a REAL declared balance -- two sources
whose transferred powers must agree -- that fails in the first window and closes
in the second.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.runtime import MultiphysicsExecutionError, conservation_status, require_conservation
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    BalanceSide, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy, TransferMeasure,
)
from engcore.scientific.multiphysics.conservation import ConservationTermBinding, CoupledConservation
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "mass_flow", "kg/s")


def _source(pid, power_at):
    spec = _spec(pid, [_port("p", "output")])

    def initialize(_t, _i, _u):
        return InitializationResult({"p": power_at(0.0)}, {"p": UNKNOWN})

    def advance(request):
        return AdvanceResult(request.end, {"p": power_at(request.start.magnitude_in("s"))}, {"p": UNKNOWN}, 1, True)

    return spec, CallbackParticipant(spec, initialize=initialize, advance=advance)


def _sink():
    spec = _spec("sink", [_port("in_a", "input"), _port("in_b", "input"), _port("out", "output")])

    def initialize(_t, _i, _u):
        return InitializationResult({"out": Quantity(0, "kg/s")}, {"out": UNKNOWN})

    def advance(request):
        return AdvanceResult(request.end, {"out": Quantity(0, "kg/s")}, {"out": UNKNOWN}, 1, True)

    return spec, CallbackParticipant(spec, initialize=initialize, advance=advance)


def _runtime(a_power, b_power, *, diagnostic=(), loss_term=False):
    (a_spec, a), (b_spec, b), (sink_spec, sink) = _source("a", a_power), _source("b", b_power), _sink()
    edges = (CouplingEdge("e_a", PortRef("a", "p"), PortRef("sink", "in_a")),
             CouplingEdge("e_b", PortRef("b", "p"), PortRef("sink", "in_b")))
    terms = [ConservationTermBinding("supplied", "e_a", BalanceSide.LEFT, TransferMeasure.SOURCE),
             ConservationTermBinding("returned", "e_b", BalanceSide.RIGHT, TransferMeasure.SOURCE)]
    if loss_term:
        terms.append(ConservationTermBinding("lost", "e_b", BalanceSide.RIGHT, TransferMeasure.LOSS, loss_form="heat"))
    balance = CoupledConservation("mass_balance", tuple(terms), Quantity(0.1, "kg/s"), "supplied equals returned")
    graph = PhysicsGraph("conservation-history", (a_spec, b_spec, sink_spec), edges, conservation=(balance,))
    plan = CouplingPlan("history-plan", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(2, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"a": a, "b": b, "sink": sink}, resolver=BulkDataResolver(store), store=store,
                               diagnostic_balances=diagnostic)


def _run(runtime, run_id="history"):
    return runtime.run(run_id, external_inputs={},
                       initial_coupling_values={"e_a": Quantity(0, "kg/s"), "e_b": Quantity(0, "kg/s")},
                       initial_coupling_uncertainty={"e_a": UNKNOWN, "e_b": UNKNOWN})


def FAIL_THEN_PASS(t):
    return Quantity(10.0 if t < 1.0 else 5.0, "kg/s")


def STEADY(_t):
    return Quantity(5.0, "kg/s")


def STEADY_G(_t):
    return Quantity(5000.0, "g/s")


def _by_window(run):
    return [(e["window_index"], e["balance_id"], e["status"], e["requirement"]) for e in run.final_outputs["_conservation"]]


def test_a_failure_in_window_0_survives_a_pass_in_window_1() -> None:
    run = _run(_runtime(FAIL_THEN_PASS, STEADY))
    assert _by_window(run) == [(0, "mass_balance", "fail", "required"), (1, "mass_balance", "pass", "required")]
    status = run.final_outputs["_conservation_status"]
    assert status["required"] == "fail"
    assert status["failed_required"] == [{"window_index": 0, "balance_id": "mass_balance"}]
    with pytest.raises(MultiphysicsExecutionError, match="required conservation did not hold"):
        require_conservation(run)


def test_every_history_entry_says_what_was_compared_against_what() -> None:
    entry = _run(_runtime(FAIL_THEN_PASS, STEADY)).final_outputs["_conservation"][0]
    assert entry["left"] == 10.0 and entry["right"] == 5.0
    assert entry["residual"] == 5.0 and entry["tolerance"] == pytest.approx(0.1)
    assert entry["declared_tolerance"] == Quantity(0.1, "kg/s").to_dict()
    assert entry["window_start"] == Quantity(0, "second").to_dict() and entry["window_end"] == Quantity(1, "second").to_dict()


def test_a_balance_that_holds_in_every_window_passes() -> None:
    run = _run(_runtime(STEADY, STEADY))
    assert run.final_outputs["_conservation_status"]["required"] == "pass"
    require_conservation(run)


def test_unit_converted_equivalent_values_give_the_same_result() -> None:
    kgs, grams = _run(_runtime(FAIL_THEN_PASS, STEADY)), _run(_runtime(FAIL_THEN_PASS, STEADY_G))
    assert _by_window(kgs) == _by_window(grams)
    assert kgs.final_outputs["_conservation_status"] == grams.final_outputs["_conservation_status"]
    for left, right in zip(kgs.final_outputs["_conservation"], grams.final_outputs["_conservation"]):
        assert Quantity(left["residual"], left["unit"]).magnitude_in("kg/s") == pytest.approx(
            Quantity(right["residual"], right["unit"]).magnitude_in("kg/s"))


def _window(index=0):
    return SimpleNamespace(index=index, start=Quantity(index, "s"), end=Quantity(index + 1, "s"))


def test_a_required_balance_whose_term_has_no_reading_refuses_the_run() -> None:
    # A window in which a balance's edge produced no transfer: the balance cannot be read.
    with pytest.raises(MultiphysicsExecutionError, match="references unexecuted edge"):
        _runtime(STEADY, STEADY)._conservation_history(_window(), {})


def test_a_diagnostic_balance_whose_term_has_no_reading_is_recorded_unknown() -> None:
    (entry,) = _runtime(STEADY, STEADY, diagnostic=("mass_balance",))._conservation_history(_window(), {})
    assert entry["status"] == "unknown" and entry["requirement"] == "diagnostic" and "unexecuted edge" in entry["reason"]
    status = conservation_status([entry], ("mass_balance",))
    assert status["diagnostic_failures"] == [{"window_index": 0, "balance_id": "mass_balance", "status": "unknown"}]


def test_a_required_entry_without_a_reading_never_passes() -> None:
    entry = {"window_index": 0, "balance_id": "mass_balance", "requirement": "required", "status": "unknown"}
    status = conservation_status([entry], ())
    assert status["required"] == "unknown" and status["unknown_required"] == [{"window_index": 0, "balance_id": "mass_balance"}]


def test_a_loss_term_on_an_edge_with_no_conversion_is_refused_when_declared() -> None:
    with pytest.raises(InvalidScientificProblem, match="with no conversion"):
        _runtime(STEADY, STEADY, loss_term=True)

def test_a_diagnostic_failure_is_retained_and_grants_nothing() -> None:
    run = _run(_runtime(FAIL_THEN_PASS, STEADY, diagnostic=("mass_balance",)))
    status = run.final_outputs["_conservation_status"]
    assert status["failed_required"] == [] and status["diagnostic_balances"] == ["mass_balance"]
    assert status["diagnostic_failures"] == [{"window_index": 0, "balance_id": "mass_balance", "status": "fail"}]
    assert [e["requirement"] for e in run.final_outputs["_conservation"]] == ["diagnostic", "diagnostic"]
    assert status["required"] == "none_required"  # nothing required was checked: never "pass"
    # The runtime's labels are a report; they cannot demote a declared balance at enforcement.
    with pytest.raises(MultiphysicsExecutionError, match="required conservation did not hold"):
        require_conservation(run)
    require_conservation(run, diagnostic=("mass_balance",))  # only the enforcing consumer can say so
    with pytest.raises(MultiphysicsExecutionError, match="undeclared"):
        require_conservation(run, diagnostic=("mass_balnce",))


def test_a_diagnostic_declaration_must_name_a_declared_balance() -> None:
    with pytest.raises(InvalidScientificProblem, match="undeclared balances"):
        _runtime(STEADY, STEADY, diagnostic=("power_balnce",))


def test_a_status_that_does_not_re_derive_from_the_history_is_refused() -> None:
    run = _run(_runtime(FAIL_THEN_PASS, STEADY))
    outputs = dict(run.final_outputs)
    outputs["_conservation_status"] = {**outputs["_conservation_status"], "required": "pass", "failed_required": []}
    with pytest.raises(MultiphysicsExecutionError, match="does not re-derive"):
        require_conservation(replace(run, final_outputs=outputs))


def test_a_history_missing_a_window_is_refused() -> None:
    run = _run(_runtime(FAIL_THEN_PASS, STEADY))
    outputs = dict(run.final_outputs)
    outputs["_conservation"] = [e for e in outputs["_conservation"] if e["window_index"] != 0]
    outputs["_conservation_status"] = conservation_status(outputs["_conservation"], ())
    with pytest.raises(MultiphysicsExecutionError, match="not recorded exactly once for every window"):
        require_conservation(replace(run, final_outputs=outputs))


def test_a_run_that_dropped_its_conservation_record_is_refused() -> None:
    run = _run(_runtime(STEADY, STEADY))
    outputs = {k: v for k, v in run.final_outputs.items() if k != "_conservation_status"}
    with pytest.raises(MultiphysicsExecutionError, match="records no conservation history"):
        require_conservation(replace(run, final_outputs=outputs))

def test_replay_reproduces_the_identical_conservation_history() -> None:
    record = _run(_runtime(FAIL_THEN_PASS, STEADY, diagnostic=("mass_balance",)))
    fresh = _runtime(FAIL_THEN_PASS, STEADY)  # participants only; the diagnostic declaration comes from the record
    store = InMemoryBulkStore()
    replayed = MultiphysicsRuntime.replay(record, fresh.participants, replay_run_id="history-replay",
                                          resolver=BulkDataResolver(store), store=store)
    assert replayed.final_outputs["_conservation"] == record.final_outputs["_conservation"]
    assert replayed.final_outputs["_conservation_status"] == record.final_outputs["_conservation_status"]


# ---- the consumers: nothing builds on a run whose required conservation failed in any window ----


def test_lifecycle_degradation_refuses_a_run_whose_required_balance_failed_earlier() -> None:
    from engcore.scenarios.lifecycle import evaluate_degradation
    from tests.test_lifecycle_engine import BATTERY_BINDINGS, _battery_model, _environment

    failed = _run(_runtime(FAIL_THEN_PASS, STEADY))
    with pytest.raises(InvalidScientificProblem, match="evaluate_degradation refuses the run: required conservation"):
        evaluate_degradation(_battery_model(), environment=_environment(), run=failed, participant_id="a",
                             bindings=BATTERY_BINDINGS)


def test_authorized_assembly_refuses_a_run_whose_required_balance_failed_earlier(monkeypatch) -> None:
    from tests.test_scientific_trust_sprint2 import _authorized

    failed = _run(_runtime(FAIL_THEN_PASS, STEADY))
    monkeypatch.setattr(MultiphysicsRuntime, "run", lambda self, *args, **kwargs: failed)
    with pytest.raises(InvalidScientificProblem, match="not an admissible coupled result: required conservation"):
        _authorized("conservation-history")

# ---- fourth review: nothing in the record is taken on trust ---------------------------------------------


def _forged(run, edit):
    outputs = dict(run.final_outputs)
    history = [dict(entry) for entry in outputs["_conservation"]]
    edit(history)
    outputs["_conservation"] = history
    outputs["_conservation_status"] = conservation_status(history, outputs["_conservation_status"]["diagnostic_balances"])
    return replace(run, final_outputs=outputs)


@pytest.mark.parametrize("edit, match", [
    (lambda h: h[0].update(requirement="diagnostic"), "required conservation did not hold"),   # relabelled
    (lambda h: h[0].update(requirement="optional"), "neither required nor diagnostic"),
    (lambda h: h[0].update(status="pass"), "its numbers say 'fail'"),                             # flipped
    (lambda h: h[0].update(tolerance=10.0, status="pass"), "the graph declares"),                  # inflated
    (lambda h: h[0].update(residual=0.0, status="pass"), r"not \|left - right\|"),
    (lambda h: h.append(dict(h[1])), "exactly once"),                                             # duplicated window
    (lambda h: h[0].update(balance_id="other"), "exactly once|undeclared"),
])
def test_a_forged_history_with_a_consistent_report_is_still_refused(edit, match) -> None:
    run = _forged(_run(_runtime(FAIL_THEN_PASS, STEADY)), edit)
    with pytest.raises(MultiphysicsExecutionError, match=match):
        require_conservation(run)


def test_an_authorized_run_read_back_with_a_failed_balance_is_refused(monkeypatch) -> None:
    from engcore.assembly.multiphysics import AuthorizedMultiphysicsRun
    from tests.test_scientific_trust_sprint2 import _authorized

    genuine = _authorized("conservation-readback").to_dict()
    failed = _run(_runtime(FAIL_THEN_PASS, STEADY))
    payload = {**genuine, "run": failed.to_dict()}
    with pytest.raises(InvalidScientificProblem, match="required conservation"):
        AuthorizedMultiphysicsRun.from_dict(payload)


def test_bind_run_refuses_a_run_whose_required_balance_failed() -> None:
    from tests.test_lifecycle_engine import _environment

    timeline = _environment().timeline
    failed = replace(_run(_runtime(FAIL_THEN_PASS, STEADY)), scenario_digest=timeline.scenario_digest)
    with pytest.raises(InvalidScientificProblem, match="bind_run refuses the run: required conservation"):
        timeline.bind_run(failed)

@pytest.mark.parametrize("a_power, refused_for_conservation", [(FAIL_THEN_PASS, True), (STEADY, False)])
def test_a_system_runtime_node_exposes_nothing_when_required_conservation_failed(a_power, refused_for_conservation) -> None:
    from engcore.system_runtime.authorities import MultiphysicsAuthority

    initial = {"e_a": Quantity(0, "kg/s"), "e_b": Quantity(0, "kg/s")}
    authority = MultiphysicsAuthority(
        "conservation-node", _runtime(a_power, STEADY),
        run_kwargs=lambda call: {"external_inputs": {}, "initial_coupling_values": initial,
                                 "initial_coupling_uncertainty": {k: UNKNOWN for k in initial}},
        outputs={"flow": "a.p"})
    call = SimpleNamespace(run_id="sys", node=SimpleNamespace(node_id="mp", commits_state=False))
    outcome = authority.execute(call)
    # The explicit fixture never reports "converged", so the node fails either way; what matters is which check
    # refuses first: conservation is checked before any output is read or any other gate runs.
    assert ("declared conservation did not hold" in outcome.reason) is refused_for_conservation, outcome.reason

def test_a_system_runtime_node_refuses_a_run_of_a_graph_it_does_not_declare() -> None:
    from engcore.system_runtime.authorities import MultiphysicsAuthority

    declared = _runtime(FAIL_THEN_PASS, STEADY)
    other = _runtime(FAIL_THEN_PASS, STEADY)
    other_graph = replace(other.graph, conservation=())  # the same participants, no balances declared
    swapped = MultiphysicsRuntime(other_graph, other.plan, other.participants, resolver=other.resolver, store=other.store)
    initial = {"e_a": Quantity(0, "kg/s"), "e_b": Quantity(0, "kg/s")}
    authority = MultiphysicsAuthority(
        "conservation-node", graph=declared.graph, plan=declared.plan, runtime_factory=lambda call: swapped,
        run_kwargs=lambda call: {"external_inputs": {}, "initial_coupling_values": initial,
                                 "initial_coupling_uncertainty": {k: UNKNOWN for k in initial}},
        outputs={"flow": "a.p"})
    outcome = authority.execute(SimpleNamespace(run_id="sys", node=SimpleNamespace(node_id="mp", commits_state=False)))
    assert outcome.status == "failed" and "different graph" in outcome.reason