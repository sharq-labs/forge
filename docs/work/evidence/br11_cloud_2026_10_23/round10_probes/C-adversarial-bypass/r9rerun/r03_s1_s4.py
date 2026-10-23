"""R8-C p03: try to re-authorize, through the PUBLIC Mind-facing API (MindWorldPort + ExecutionDesk.gateway()), an
admitted action whose bound budget account moved past it, under round 7's BEHIND / REWRITE rule.  The execution side
uses its normal configuration: BudgetReader.following over a mapping it updates (restores replace the object, as
sria.campaign does).  An intervening verification (a Mind admission request) observes every move."""
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import ExecutionDesk, FeasibleActionSpace, MindWorldPort, project_world
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def setup():
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    eid = next(iter(o.experiments))
    auth = o.authorities()
    log = []

    def executor(authorization):
        log.append(authorization.admitted_digest)
        o.ledgers[lid].settle(charge_id=f"run-{len(log)}", action_id="simulate_pulse", iteration=len(log),
                              family=ActionFamily.EXPLORE, realized=1.0)
        return "ran"

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, auth)))
    return o, lid, eid, gw, port, log, auth


def try_dispatch(port, admitted, gw):
    try:
        port.execute(admitted, gw)
        return "DISPATCHED"
    except Exception as exc:  # noqa: BLE001
        return f"refused ({str(exc)[:110]})"


def observe(o, port, gw):
    r = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gw)
    return f"{r.status.value} {r.codes()}"


# S1 rollback then IDENTICAL re-extension
o, lid, eid, gw, port, log, _ = setup()
r = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gw)
s0 = o.ledgers[lid].to_dict()
print("S1 dispatch #1:", try_dispatch(port, r.admitted, gw), "| observe:", observe(o, port, gw))
s1 = o.ledgers[lid].to_dict()
o.ledgers[lid] = BudgetLedger.from_dict(s0)
print("S1 after rollback: observe", observe(o, port, gw), "| dispatch A:", try_dispatch(port, r.admitted, gw))
o.ledgers[lid] = BudgetLedger.from_dict(s1)
print("S1 identical re-extension: observe", observe(o, port, gw), "| dispatch A:", try_dispatch(port, r.admitted, gw))
print("S1 executor ran", len(log))

# S2 rollback then a DIFFERENT same-length re-extension, then back to the original
o, lid, eid, gw, port, log, _ = setup()
r = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gw)
s0 = o.ledgers[lid].to_dict()
print("S2 dispatch #1:", try_dispatch(port, r.admitted, gw), "| observe:", observe(o, port, gw))
s1 = o.ledgers[lid].to_dict()
o.ledgers[lid] = BudgetLedger.from_dict(s0)
print("S2 rolled back: observe", observe(o, port, gw))
o.ledgers[lid].settle(charge_id="other", action_id="x", iteration=9, family=ActionFamily.EXPLORE, realized=1.0)
print("S2 other same-length history: observe", observe(o, port, gw))
o.ledgers[lid] = BudgetLedger.from_dict(s0)
print("S2 back to the admitted state: observe", observe(o, port, gw), "| dispatch A:",
      try_dispatch(port, r.admitted, gw))
print("S2 executor ran", len(log))

# S3 removal and re-adding (rolled back), then the original
o, lid, eid, gw, port, log, _ = setup()
r = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gw)
s0 = o.ledgers[lid].to_dict()
print("S3 dispatch #1:", try_dispatch(port, r.admitted, gw), "| observe:", observe(o, port, gw))
s1 = o.ledgers[lid].to_dict()
del o.ledgers[lid]
print("S3 removed: observe", observe(o, port, gw))
o.ledgers[lid] = BudgetLedger.from_dict(s0)
print("S3 re-added rolled back: observe", observe(o, port, gw), "| dispatch A:", try_dispatch(port, r.admitted, gw))
print("S3 executor ran", len(log))

# S4 experiment returns to an earlier content digest (an evaluation recorded, then the experiment restored)
o, lid, eid, gw, port, log, _ = setup()
r = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gw)
e0 = o.experiments[eid].to_dict()
o.experiments[eid].record(ScientificEvaluation("extra.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="spend"))
print("S4 recorded one evaluation: observe", observe(o, port, gw))
o.experiments[eid] = ScientificExperiment.from_dict(e0)
print("S4 restored: observe", observe(o, port, gw), "| dispatch A:", try_dispatch(port, r.admitted, gw))
o.experiments[eid].metadata["k"] = "v"
print("S4 restored + metadata move: observe", observe(o, port, gw), "| dispatch A:", try_dispatch(port, r.admitted, gw))
print("S4 executor ran", len(log))

# S5 snapshots taken while another thread settles charges in place (and restores never happen): no account may be
