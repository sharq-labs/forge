"""GEN2-BR1.1 review round 1: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md section 9).

Lens A (scientific authority), B (architecture), C (adversarial bypass), D (replay / stale).  Each test reproduces the
reviewer's attack on the repaired code and pins the refusal.  The interval-semantics findings (A-F1, A-F2, A-F3, B7)
are pinned in ``test_authority_failing_first.py`` (control A) and the BR1 contract tests.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import pathlib
import re

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (
    AdmissionGateway, AdmissionRecord, Authorities, BindingStatus, BudgetSource, DispatchAuthorization,
    DispatchRefused, ExecutionDesk, FeasibilityStatus as F, FeasibleActionSpace, Lineage, MindWorldPort,
    OwnerKind, ProtocolDeclaration, ScientificWorld, WorldBudget, WorldRefused, admit, authorize_dispatch,
    replay_admission, verify_authorization, verify_lineage, verify_world,
)
from engcore.mind.world import admission as adm
from engcore.mind.world.admission import DECLARATION_PROVENANCE
from engcore.mind.world.authority import DECLARATION_HELD
from engcore.mind.world.base import digest
from engcore.mind.world.owners import (
    BudgetReader, DeclarationReader, FrozenReader, RunStateReader, frozen_readers, is_live,
)
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.sria.decision.replay import ReplayOutcome

SIM = ax.br1.base("battery")["simulate_pulse"]
POOL_OK = {"I_A": ax.q(1.0, "A"), "t_on_s": ax.q(60, "s")}
POOL_OFF = {"I_A": ax.q(1.15, "A"), "t_on_s": ax.q(60, "s")}
SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "engcore" / "mind" / "world"


def _space(w):
    return FeasibleActionSpace.build(w)


def _codes(r) -> set[str]:
    return {x.code for x in r.reasons}


def _edit(record, **fields) -> None:
    """An in-place edit of a frozen record, the way an adversarial holder of the object would make it."""
    for name, value in fields.items():
        object.__setattr__(record, name, value)


def _admitted(o, aid, assignments, observe=()):
    r = admit(_space(o.world), o.propose(aid, assignments, observe), o.authorities())
    assert r.admitted is not None, r.codes()
    return r.admitted


# ---- C-F1 / D-F1 (BLOCKER): admission never decides on the caller's object -------------------------------------------
def _pool_with_off_level(o):
    """The Mind's world with a 1.15 A level slipped into the pool current's declared levels, in place."""
    w = ScientificWorld.from_dict(o.world.to_dict())                  # the Mind's own copy (as a port holds it)
    domain = w.action("pool_query").control("I_A").domain
    _edit(domain, levels=tuple(domain.levels) + (ax.q(1.15, "A"),))
    return w


def test_a_world_edited_in_place_is_never_verified_admitted_or_dispatched():
    o = ax.gen1_pool()
    honest = admit(_space(o.world), o.propose("pool_query", POOL_OFF), o.authorities())
    assert honest.status is F.INFEASIBLE_PROTOCOL and "LEVEL_NOT_DECLARED" in _codes(honest)
    w = _pool_with_off_level(o)
    assert not w.intact()
    report = verify_world(w, o.authorities())
    assert not report.ok and {c.subject for c in report.failures()} == {"identity"}
    space = object.__new__(FeasibleActionSpace)                       # a space over the edited object
    _edit(space, world=w, entries=_space(o.world).entries, space_id=_space(o.world).space_id)
    with pytest.raises(WorldRefused, match="identity names"):
        admit(space, o.propose("pool_query", POOL_OFF, world=w), o.authorities())


def test_an_edited_copy_that_also_restates_its_cached_identity_is_not_the_projection():
    o = ax.owned("battery")
    w = ScientificWorld.from_dict(o.world.to_dict())
    _edit(w, constraints=())                                          # the mode-dependent current limits, dropped
    content = digest(w._material())
    _edit(w, _content=content, _revision=digest({"world_id": w.world_id, "content": content, **w.lineage.identity()}))
    assert w.intact()                                                 # self-consistent, so it rebuilds...
    r = admit(_space(w), o.propose("simulate_pulse", *SIM, world=w), o.authorities())
    assert r.admitted is None and "AUTHORITY_MISMATCH" in r.codes()   # ...but its owners do not project it


@pytest.mark.parametrize("edit", ["constraints_dropped", "state_relabelled_declared", "gating_emptied", "unit_edited"])
def test_every_declared_fact_edited_in_place_after_admission_is_refused_at_dispatch(edit):
    o = ax.owned("battery")
    a = _admitted(o, "simulate_pulse", *SIM)
    w = a.world                                                       # the admitted action's own world object
    if edit == "constraints_dropped":
        _edit(w, constraints=())
    elif edit == "state_relabelled_declared":
        soc = w.variable("SOC")
        _edit(soc, origin=ax.ValueOrigin.DECLARED, source=None, value=ax.q(0.5, "dimensionless"))
    elif edit == "gating_emptied":
        _edit(w.action("simulate_pulse"), applicability=())
    else:
        decl = w.variable("I").declaration
        _edit(decl, unit="milliampere")
    calls = []
    with pytest.raises(DispatchRefused):
        ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True).dispatch(a)
    assert calls == []


def test_a_world_shares_no_object_with_the_declaration_in_force():
    o = ax.gen1_pool()
    before = o.declaration.digest
    domain = o.world.action("pool_query").control("I_A").domain
    _edit(domain, levels=tuple(domain.levels) + (ax.q(1.15, "A"),))   # an edit through the projected world
    assert o.declaration.digest == before                             # the declaration in force is untouched
    fresh = ax.project_world(o.declaration, o.authorities())
    assert [x.magnitude for x in fresh.action("pool_query").control("I_A").domain.levels] == [1.0, 2.0]


def test_a_port_copy_edited_in_place_changes_nothing_the_execution_side_admits():
    o = ax.gen1_pool()
    gateway = ExecutionDesk(o.authorities(), lambda auth: auth, accept_synthetic=True).gateway()
    port = MindWorldPort(_space(o.world))
    domain = port.world.action("pool_query").control("I_A").domain
    _edit(domain, levels=tuple(domain.levels) + (ax.q(1.15, "A"),))
    with pytest.raises(WorldRefused):
        port.request_admission(o.propose("pool_query", POOL_OFF), gateway)


# ---- C-F2 (MAJOR): the Mind holds a gateway, never the desk; the desk is immutable; the executor re-derives ---------------
def test_the_desk_is_immutable_and_the_mind_is_handed_only_its_gateway():
    o = ax.owned("battery")
    desk = ExecutionDesk(o.authorities(), lambda auth: auth, accept_synthetic=True)
    for name, value in (("_authorities", Authorities.of()), ("_accept_synthetic", True), ("_executor", print)):
        with pytest.raises(WorldRefused, match="immutable"):
            setattr(desk, name, value)
    gateway = desk.gateway()
    assert type(gateway) is AdmissionGateway
    assert {n for n in dir(gateway) if not n.startswith("__")} == {"_admit", "_dispatch", "admit", "dispatch"}
    with pytest.raises(WorldRefused, match="immutable"):
        gateway._admit = None
    port = MindWorldPort(_space(o.world))
    with pytest.raises(WorldRefused, match="never handed the desk"):
        port.request_admission(o.propose("simulate_pulse", *SIM), desk)
    r = port.request_admission(o.propose("simulate_pulse", *SIM), gateway)
    assert r.admitted is not None
    assert isinstance(port.execute(r.admitted, gateway), DispatchAuthorization)


def test_the_executor_behind_a_desk_re_derives_every_authorization_however_it_is_reached():
    o = ax.owned("battery")
    calls = []
    desk = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True)
    a = _admitted(o, "simulate_pulse", *SIM)
    genuine = authorize_dispatch(a, o.authorities(), accept_synthetic=True)
    with adm._minting():                                              # an authorization minted by hand, edited
        forged = dataclasses.replace(genuine, configuration=(("I", ax.q(9, "A")),))
    with pytest.raises(DispatchRefused, match="edited or forged"):
        desk._executor(forged)                                        # reached past the desk's dispatch
    with pytest.raises(DispatchRefused):
        verify_authorization(forged, o.authorities(), accept_synthetic=True)
    assert verify_authorization(genuine, o.authorities(), accept_synthetic=True).digest == genuine.digest
    desk._executor(genuine)
    assert len(calls) == 1 and calls[0].digest == genuine.digest


# ---- B1 / B4 / C-M2 / D-F3: liveness is derived; only live readers back a dispatch -----------------------------------------
def test_liveness_is_derived_from_the_readers_and_never_asserted():
    o = ax.owned("battery")
    live = o.authorities()
    assert live.live and all(is_live(r) for r in live.readers)
    a = _admitted(o, "simulate_pulse", *SIM)
    record = AdmissionRecord.of(admit(_space(o.world), o.propose("simulate_pulse", *SIM), live), live)
    snapshot = Authorities.from_snapshot(record.snapshot)
    relabelled = Authorities(snapshot.readers)                        # a snapshot's readers handed in again
    fixed_state = Authorities.of(*(RunStateReader(o.run.checkpoint) if type(r) is RunStateReader else r
                                   for r in live.readers))
    fixed_decl = Authorities.of(*(DeclarationReader((o.declaration,)) if type(r) is DeclarationReader else r
                                  for r in live.readers))

    class LookAlike:                                                  # a duck-typed reader that says it is live
        live = True
        kinds = frozenset({OwnerKind.BUDGET_LEDGER, OwnerKind.EXPERIMENT})
        owner_id = "budget"

        def __init__(self, inner):
            self.inner = inner

        def read(self, kind, record_id):
            return self.inner.read(kind, record_id)

        def superseded(self, kind, record_id):
            return None

        def project(self, record, fields):
            return self.inner.project(record, fields)

    duck = Authorities.of(*(LookAlike(r) if type(r) is BudgetReader else r for r in live.readers))
    for authorities in (snapshot, relabelled, fixed_state, fixed_decl, duck):
        assert not authorities.live
        with pytest.raises(WorldRefused):
            ExecutionDesk(authorities, lambda auth: auth, accept_synthetic=True)
        with pytest.raises(DispatchRefused, match="live owner readers"):
            authorize_dispatch(a, authorities, accept_synthetic=True)
    auth = authorize_dispatch(a, live, accept_synthetic=True)
    assert ("system_state", o.run.request.digest) in auth.owners and ["system_state", o.run.request.digest] in \
        auth.to_dict()["owners"]


def test_a_followed_head_of_another_run_or_an_unanswerable_head_is_owner_unavailable():
    o = ax.owned("battery")
    other = ax.run_state("battery.another-run", {"cell": ("component", {
        "SOC": (ax.q(0.5, "dimensionless"), ax.covered(ax.q(0.45, "dimensionless"), ax.q(0.55, "dimensionless"))),
        "R0": (ax.q(0.012, "ohm"), ax.Uncertainty.unknown("not quantified"))})})
    heads = [o.run.checkpoint]
    authorities = o.authorities(state=None)
    reader = RunStateReader.following(lambda: heads[0])
    swapped = Authorities.of(*(reader if type(r) is RunStateReader else r for r in authorities.readers))
    assert verify_world(o.world, swapped).ok
    heads[0] = other.checkpoint
    report = verify_world(o.world, swapped)
    assert {c.status for c in report.failures()} == {BindingStatus.OWNER_UNAVAILABLE}

    def broken():
        raise RuntimeError("the execution side lost its run")
    failing = Authorities.of(*(RunStateReader.following(lambda: o.run.checkpoint) if type(r) is RunStateReader
                               else r for r in authorities.readers))
    object.__setattr__(failing.reader(OwnerKind.SYSTEM_STATE), "_follow", broken)
    assert {c.status for c in verify_world(o.world, failing).failures()} == {BindingStatus.OWNER_UNAVAILABLE}


def test_a_declaration_revision_restated_with_other_content_is_refused():
    o = ax.owned("battery")
    held = [o.declaration]
    reader = DeclarationReader.following(lambda: held)
    authorities = Authorities.of(*(reader if type(r) is DeclarationReader else r for r in o.authorities().readers))
    assert verify_world(o.world, authorities).ok
    held[0] = dataclasses.replace(o.declaration, basis=o.declaration.basis + " (quietly changed)")   # same revision
    failures = verify_world(o.world, authorities).failures()
    assert failures and {c.status for c in failures} == {BindingStatus.OWNER_UNAVAILABLE}


# ---- B5 / A-F5 / D-F7: provider currency is the registry's; the execution side may re-probe ----------------------------------
def test_a_provider_that_went_down_in_the_same_registry_is_refused_when_the_execution_side_re_probes():
    o = ax.owned("battery")
    a = _admitted(o, "simulate_pulse", *SIM)
    o.take_down("sim.ecm")
    cached = authorize_dispatch(a, o.authorities(), accept_synthetic=True)        # the registry's cached probe
    assert cached.admitted_digest == a.digest
    with pytest.raises(DispatchRefused, match="AUTHORITY_STALE"):
        authorize_dispatch(a, o.authorities(refresh=True), accept_synthetic=True)


# ---- B2 / A-F4 / B3 / C-M3: one account states one dimension, in a unit that fits it -------------------------------------
def test_one_budget_account_never_states_two_dimensions():
    o = ax.owned("battery")
    solver = next(b for b in o.declaration.budget if b.dimension == "solver_calls")
    with pytest.raises(WorldRefused, match="one budget account states one dimension"):
        dataclasses.replace(o.declaration, budget=tuple(b for b in o.declaration.budget if b.dimension != "cost") +
                            (BudgetSource.ledger("cost", solver.ref),))
    statements = o.world.budget.statements
    s = next(x for x in statements if x.dimension == "solver_calls")
    with pytest.raises(WorldRefused, match="one budget account states one dimension"):
        WorldBudget(unbounded=tuple(x for x in o.world.budget.unbounded if x[0] != "cost"),
                    statements=statements + (dataclasses.replace(s, dimension="cost"),), projected=True)


@pytest.mark.parametrize("dimension,unit,ok", [("solver_calls", "hour", False), ("solver_calls", "second", False),
                                                ("solver_calls", "dimensionless", True), ("wall_time", "hour", True),
                                                ("wall_time", "dimensionless", False)])
def test_a_ledger_accounts_in_a_unit_that_fits_its_dimension(dimension, unit, ok):
    o = ax.owned("hvac_chamber")                                      # states both solver calls and wall time
    ref = next(b.ref for b in o.declaration.budget if b.dimension == dimension and b.kind == "ledger")
    o.ledgers[ref] = ax.ledger(100, 0, unit, ref)
    if ok:
        assert ax.project_world(o.declaration, o.authorities()).budget.statement(dimension) is not None
    else:
        with pytest.raises(WorldRefused, match="convertible|does not know"):
            ax.project_world(o.declaration, o.authorities())


def test_an_amount_the_unit_owner_cannot_convert_into_the_ledger_unit_is_never_compared_raw():
    o = ax.owned("hvac_chamber")
    statement = o.world.budget.statement("wall_time")
    assert statement.decide(ax.q(1, "hour"), ax.ActionFamily.EXPLORE)[0] in (True, False)   # a duration converts
    with pytest.raises(WorldRefused, match="does not convert"):
        statement.decide(ax.q(2, "meter"), ax.ActionFamily.EXPLORE)               # a length is never seconds
    from engcore.mind.world.feasibility import REASON_CODES, CheckFamily
    assert "BUDGET_UNIT_INCOMPATIBLE" in REASON_CODES[CheckFamily.BUDGET]


# ---- A-F10 / B8 / C-M6: the observation-budget rule restated from the owner, pinned to it -----------------------------------
@pytest.mark.parametrize("max_obs,max_attempts,spent,failed", [(3, None, 0, 0), (3, None, 2, 0), (3, 5, 1, 3),
                                                               (4, 4, 2, 2), (2, 6, 2, 0), (5, 5, 0, 5)])
def test_the_world_observation_rule_agrees_with_what_the_experiment_owner_records(max_obs, max_attempts, spent, failed):
    from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
    exp = ScientificExperiment("e", ax.ScientificProblem("e.problem"), ExperimentBudget(max_obs, max_attempts))
    for i in range(failed):
        exp.record(ScientificEvaluation(f"f{i}", {}, status=EvaluationStatus.FAILED))
    for i in range(spent):
        exp.record(ScientificEvaluation(f"s{i}", {}, status=EvaluationStatus.NOT_CONVERGED))
    record = BudgetReader(experiments={"e": exp}).read(OwnerKind.EXPERIMENT, "e")
    projected = {k: record.payload[k] for k in ("accounting", "budget")}
    from engcore.mind.world import BudgetStatement
    statement = BudgetStatement("experiments", "experiment", projected,
                                   record.binding(("accounting", "budget"), projected))
    for n in range(1, max_obs + 3):
        owner = copy.deepcopy(exp)
        try:
            for i in range(n):
                owner.record(ScientificEvaluation(f"n{i}", {}, status=EvaluationStatus.NOT_CONVERGED))
            owner_ok = True
        except Exception:  # noqa: BLE001 - the owner refusing is the answer
            owner_ok = False
        assert statement.decide(n, None)[0] is owner_ok, (n, owner_ok)


# ---- D-F2 (MAJOR): replay re-derives every recorded owner identity --------------------------------------------------------
def _record(o, aid, assignments):
    r = admit(_space(o.world), o.propose(aid, *assignments), o.authorities())
    return r, json.loads(json.dumps(AdmissionRecord.of(r, o.authorities()).to_dict()))


def test_a_forged_snapshot_payload_under_a_genuine_owner_digest_does_not_replay():
    o = ax.owned("battery")
    hot = ({**SIM[0], "T_amb": ax.q(55, "degC")}, SIM[1])
    r, record = _record(o, "simulate_pulse", hot)
    assert r.status is F.INFEASIBLE_APPLICABILITY and replay_admission(record).outcome is ReplayOutcome.REPRODUCED
    forged = copy.deepcopy(record)
    for item in forged["snapshot"]["records"]:
        if item["owner_kind"] == "model_record":
            cond = item["record"]["payload"]["model"]["validity"]["conditions"][0]
            cond["maximum"]["magnitude"] = 60.0                    # widened, the registry digest kept
    out = replay_admission(forged)
    assert out.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE and "re-derive" in out.detail
    state = copy.deepcopy(record)
    for item in state["snapshot"]["records"]:
        if item["owner_kind"] == "system_state":
            item["record"]["payload"]["value"]["magnitude"] = 0.5     # another value under the genuine head digest
    assert replay_admission(state).outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE


def test_an_admission_is_recorded_only_against_the_live_owners():
    o = ax.owned("battery")
    r, record = _record(o, "simulate_pulse", SIM)
    with pytest.raises(WorldRefused, match="live owners"):
        AdmissionRecord.of(r, Authorities.from_snapshot(record["snapshot"]))


def test_frozen_readers_refuse_a_record_its_owner_rule_refutes_for_every_owner_kind():
    o = ax.owned("battery")
    _, record = _record(o, "simulate_pulse", SIM)
    kinds = {item["owner_kind"] for item in record["snapshot"]["records"]}
    assert {"declaration", "unit_registry", "system_state", "model_record", "provider_status", "budget_ledger",
            "experiment"} <= kinds
    frozen_readers(record["snapshot"])                                # the genuine snapshot is accepted
    for kind in sorted(kinds):
        forged = copy.deepcopy(record["snapshot"])
        item = next(i for i in forged["records"] if i["owner_kind"] == kind)
        item["record"]["record_digest"] = hashlib.sha256(f"another {kind}".encode()).hexdigest()
        with pytest.raises(WorldRefused, match="re-derive"):
            frozen_readers(forged)


# ---- D-F5: the snapshot holds exactly what the verification read, so a refusal replays too ---------------------------------
def test_a_refused_admission_replays_as_reproduced():
    o = ax.owned("battery")
    w = o.world
    soc = w.variable("SOC")
    unbound = w.derive(reason="unbound copy", variables=tuple(
        dataclasses.replace(v, value=None, origin=None, source=None, uncertainty=ax.Uncertainty.unknown("dropped"))
        if v is soc else v for v in w.variables))
    r = admit(_space(unbound), o.propose("simulate_pulse", *SIM, world=unbound), o.authorities())
    assert r.admitted is None and "AUTHORITY_MISMATCH" in r.codes()
    record = json.loads(json.dumps(AdmissionRecord.of(r, o.authorities()).to_dict()))
    assert replay_admission(record).outcome is ReplayOutcome.REPRODUCED


# ---- D-F6 / C-M1: a projection carries no history its owners cannot verify --------------------------------------------------
def test_a_world_with_an_invented_lineage_is_not_the_projection():
    o = ax.owned("battery")
    w = o.world
    forged = dataclasses.replace(w, lineage=Lineage(7, hashlib.sha256(b"never").hexdigest(), "never happened",
                                                    ("variables",)))
    report = verify_world(forged, o.authorities())
    assert not report.ok and {c.subject for c in report.failures()} == {"projection"}
    r = admit(_space(forged), o.propose("simulate_pulse", *SIM, world=forged), o.authorities())
    assert r.admitted is None and "AUTHORITY_MISMATCH" in r.codes()


# ---- D-F8: lineage version 1 (BR1) keeps its bytes and verifies by walking the store ---------------------------------------
def test_a_br1_lineage_without_ancestor_statements_rebuilds_and_verifies_and_still_refuses_laundering():
    w = ax.br1.battery_world()
    child = w.derive(reason="a restated basis", basis=w.basis + " (restated)")
    legacy = dataclasses.replace(child, lineage=dataclasses.replace(child.lineage, bound=()))   # BR1's shape
    payload = legacy.to_dict()
    assert payload["lineage"]["schema"].endswith("lineage/1") and "bound" not in payload["lineage"]
    assert ScientificWorld.from_dict(payload).revision_id == legacy.revision_id
    if child.lineage.bound:
        assert child.to_dict()["lineage"]["schema"].endswith("lineage/2")
    assert verify_lineage(legacy, {w.revision_id: w}) == (w.revision_id, legacy.revision_id)
    soc = w.variable("SOC")
    unbound = dataclasses.replace(w, variables=tuple(dataclasses.replace(
        v, value=None, origin=None, source=None, uncertainty=ax.Uncertainty.unknown("withdrawn")) if v is soc else v
        for v in w.variables), lineage=Lineage(1, w.revision_id, "withdrawn", ("variables",)))
    rebound = dataclasses.replace(w, variables=tuple(dataclasses.replace(
        v, value=ax.q(0.05, "dimensionless"), uncertainty=ax.br1.interval(0.05, 0.02, "dimensionless"))
        if v.name == "SOC" else v for v in w.variables),
                                  lineage=Lineage(2, unbound.revision_id, "re-bound", ("variables",)))
    with pytest.raises(WorldRefused, match="already carried another value"):
        verify_lineage(rebound, {w.revision_id: w, unbound.revision_id: unbound})


# ---- A-F7: the declaration is reported as held in force, not as an owner fact ------------------------------------------------
def test_the_declaration_is_reported_held_in_force_down_to_the_executor():
    o = ax.owned("battery")
    report = verify_world(o.world, o.authorities())
    decl = [c for c in report.checks if c.owner_kind is OwnerKind.DECLARATION and c.subject == "declaration"]
    assert decl and all(c.detail["provenance"] == DECLARATION_HELD for c in decl)
    auth = authorize_dispatch(_admitted(o, "simulate_pulse", *SIM), o.authorities(), accept_synthetic=True)
    payload = auth.to_dict()
    assert payload["declaration_provenance"] == DECLARATION_PROVENANCE
    assert payload["declaration"]["record_digest"] == o.declaration.digest


# ---- A-F13: definite verdicts are exported only from a verified admission -------------------------------------------------
def test_sria_verdicts_are_exported_only_from_an_admission_on_a_verified_world():
    o = ax.gen1_pool()
    r = admit(_space(o.world), o.propose("pool_query", POOL_OFF), o.authorities())
    assert r.verification.ok and r.feasibility_verdicts() and all(not v.feasible for v in r.feasibility_verdicts())
    stale = admit(_space(o.world), o.propose("pool_query", POOL_OFF),
                  o.authorities(declarations=(dataclasses.replace(o.declaration, revision=2),)))
    assert not stale.verification.ok and stale.feasibility_verdicts() == ()


# ---- C-M5: intake normalizes keys and refuses smuggled value payloads -------------------------------------------------------
@pytest.mark.parametrize("key", ["ADMİTTED", "ｆeasible", "admi​ssion", " Admitted "])
def test_look_alike_authority_keys_are_refused_at_intake(key):
    from engcore.mind.world import IntakeRefusal, proposed_action_from_suggestion
    from engcore.scientific.ir.values import encode_value
    from engcore.sria.decision.external import ExternalSuggestion, SuggestionRefused
    from engcore.sria.decision.hypotheses import ProposerKind
    o = ax.gen1_pool()
    value = {**encode_value(ax.q(1.0, "A")), key: True}
    point = {"assignments": [{"variable": "I_A", "value": value},
                             {"variable": "t_on_s", "value": encode_value(ax.q(60, "s"))}]}
    try:
        s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", o.declaration.actions[0].family,
                               "pool_query", point, "r", None, {"world_revision": o.world.revision_id})
    except SuggestionRefused:
        return
    assert isinstance(proposed_action_from_suggestion(s, world=o.world), IntakeRefusal)


# ---- B11: the boundary, statically ------------------------------------------------------------------------------------------
def test_the_owner_readers_call_no_owner_mutation_and_the_world_package_imports_no_executor():
    owners = (SRC / "owners.py").read_text()
    for call in (".settle(", ".record(", ".register(", ".reserve(", ".charge(", ".mark(", ".once(", ".run("):
        assert call not in owners, call
    for path in SRC.glob("*.py"):
        text = path.read_text()
        assert not re.search(r"system_runtime\.executor|import SystemExecutor|execution\.orchestration\.runner", text), \
            path.name
