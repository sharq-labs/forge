"""R11-C c1112: round 10 moved the experiment read-back's copy.deepcopy(back) (owners.py:409) OUTSIDE the try that
classifies read-back failures.  The owner writes an experiment whose metadata is nested a few hundred levels deep
(json's C encoder/decoder and ScientificExperiment.from_dict accept it), but the reader's own deepcopy raises
RecursionError, which escapes _account/_read_back/_observe_all (only _Unreadable/OwnerUnavailable are caught), escapes
BudgetReader.pinned() (not an OwnerUnavailable), is kept by _Memo as a pin error and re-raised at every budget read,
and escapes Authorities.check (it catches OwnerUnavailable and WorldRefused only), admit(), the gateway and
authorize_dispatch (it catches WorldRefused, ScientificCoreError, AttributeError, TypeError, KeyError, ValueError).

Consequences checked through ExecutionDesk.gateway():
  (1) the minimal depth, and that EVERY admission through the desk raises (also a world that never reads that account);
  (2) the handed state is never compared (no history recorded, not refused for good): the executor's run records an
      observation and the deep metadata; Mind admissions raise; the execution side restores the pre-run checkpoint;
      the Mind re-dispatches the same admitted action -> executed again?  Control: the same run with shallow metadata.
At c69e579 the deepcopy was inside the try (a per-verification OwnerUnavailable)."""
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def nested(depth):
    root = node = {}
    for _ in range(depth):
        node["parent"] = {}
        node = node["parent"]
    return root


def minimal_depth():
    for depth in (100, 200, 250, 300, 350, 400, 500, 700, 1000):
        o = ax.owned("battery")
        o.experiments["side.campaign"] = ax.experiment("side.campaign", 10, 1)
        gw = ExecutionDesk(o.authorities(), lambda a: "ran", accept_synthetic=True).gateway()   # built first
        o.experiments["side.campaign"].metadata["provenance"] = nested(depth)                      # then it moves
        try:
            r = gw.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM))
            out = r.status.value
        except Exception as exc:  # noqa: BLE001
            out = f"RAISED {type(exc).__name__}"
        print(f"  unbound side experiment, metadata depth {depth}: admission of a world that never reads it -> {out}")
        if out.startswith("RAISED"):
            return depth
    return None


def redispatch(depth):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    calls = []

    def executor(authorization):
        calls.append(1)
        exp = o.experiments[eid]
        exp.record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        exp.metadata["provenance"] = nested(depth)                        # the run's provenance chain

    auth = o.authorities()
    gateway = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    space = FeasibleActionSpace.build(o.world)
    r = gateway.admit(space, o.propose("simulate_pulse", *SIM))
    checkpoint = o.experiments[eid].to_dict()
    gateway.dispatch(r.admitted)
    seen = []
    for _ in range(2):                                                    # Mind requests on the spent state
        try:
            a = gateway.admit(space, o.propose("simulate_pulse", *SIM))
            seen.append(f"{a.status.value} {a.codes()}")
        except Exception as exc:  # noqa: BLE001
            seen.append(f"RAISED {type(exc).__name__}")
    o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)       # restore (object replaced)
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:70]})"
    except Exception as exc:  # noqa: BLE001
        d = f"RAISED {type(exc).__name__}"
    print(f"  metadata depth {depth}: requests on the spent state: {seen} | re-dispatch after the restore: {d} | "
          f"executor ran {len(calls)}")


print(f"recursion limit {sys.getrecursionlimit()}")
print("(1)")
d = minimal_depth()
print("(2)")
redispatch(3)
redispatch(d or 1000)
redispatch(600)
