"""Independent skeptic probe for F11-1 (written from scratch, public API only).

Sequential: admit -> dispatch #1 (executor records one evaluation, and puts a deep, owner-readable trace in the
experiment's metadata, or in the evaluation's own metadata) -> one verification is handed the spent state
(reader.read, then a full admit) -> the execution side restores its pre-run checkpoint -> re-dispatch.
Also checks the owner itself writes the spent state down and reads it back (to_json/from_dict, and to_dict/from_dict).
"""
import json
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import to_json
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def nest(n):
    x = [0]
    for _ in range(n):
        x = [x]
    return x


def go(depth, where, verify):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    assert r.admitted is not None
    checkpoint = ScientificExperiment.from_dict(json.loads(to_json(o.experiments[eid])))
    calls = []

    def executor(authorization):
        calls.append(1)
        md = {"trace": nest(depth)} if where == "evaluation" else {}
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="pulse", metadata=md))
        if where == "experiment":
            o.experiments[eid].metadata["trace"] = nest(depth)

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    gw.dispatch(r.admitted)
    # owner's own round trips on the spent state
    exp = o.experiments[eid]
    own1 = len(ScientificExperiment.from_dict(json.loads(to_json(exp))).evaluations)
    own2 = len(ScientificExperiment.from_dict(exp.to_dict()).evaluations)
    if verify == "read":
        try:
            reader.read(OwnerKind.EXPERIMENT, eid)
            v = "read ok"
        except OwnerUnavailable as exc:
            v = f"OwnerUnavailable: {str(exc)[:60]}"
        except BaseException as exc:  # noqa: BLE001
            v = f"RAISED {type(exc).__name__}"
    elif verify == "admit":
        try:
            res = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
            v = f"admit -> {res.status.value}"
        except BaseException as exc:  # noqa: BLE001
            v = f"RAISED {type(exc).__name__}"
    else:
        v = "no verification between"
    o.experiments[eid] = checkpoint
    try:
        gw.dispatch(r.admitted)
        d = "DISPATCHED"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:60]})"
    except BaseException as exc:  # noqa: BLE001
        d = f"RAISED {type(exc).__name__}"
    return f"owner round trips: {own1}/{own2} evals | verification on spend: {v} | re-dispatch after restore: {d} | " \
           f"executor ran {len(calls)}"


depths = [int(a) for a in sys.argv[1:]] or [3, 600]
for where in ("experiment",):
    for verify in ("read", "admit", "none"):
        for depth in depths:
            print(f"[{where:10s} {verify:5s} depth {depth:4d}] {go(depth, where, verify)}")
