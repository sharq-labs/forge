"""Skeptic re-run of R10-C-F1, written independently of the lens probe.

Uses only the fixture's own execution-side authorities (o.authorities(): BudgetReader.following over the live
mapping), admit, and the desk's gateway.  Sequence per variant:
  1. admit simulate_pulse; dispatch once (the executor records one evaluation, in place).
  2. a SEPARATE verification is handed the spent state: a fresh admission of the same proposal.
  3. the execution side restores the pre-run experiment from a JSON checkpoint (object replaced).
  4. re-dispatch the SAME AdmittedAction.
Variants: evaluation metadata none / flat / nested list / nested dict / tuple, and (V6) the pre-run experiment itself
restored from JSON where an EARLIER evaluation carried nested metadata (availability check).
Also prints what _plain says about the spent experiment's to_dict and which value types it contains."""
import json

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.mind.world.owners import _plain
from engcore.scientific import to_json
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def types_in(x, acc):
    acc.add(type(x).__name__)
    if isinstance(x, dict) or type(x).__name__ == "FrozenMapping":
        for v in x.values():
            types_in(v, acc)
    elif isinstance(x, (list, tuple)) or type(x).__name__ == "FrozenList":
        for v in x:
            types_in(v, acc)
    return acc


def run(label, meta):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    auth = o.authorities()
    space = FeasibleActionSpace.build(o.world)
    r = admit(space, o.propose("simulate_pulse", *SIM), auth)
    assert r.admitted is not None, r
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"v01.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata=meta))
        return "ran"

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    checkpoint = json.loads(to_json(o.experiments[eid]))         # pre-run JSON checkpoint
    gw.dispatch(r.admitted)
    spent = o.experiments[eid]
    plain = _plain(spent.to_dict())
    owner_back = len(ScientificExperiment.from_dict(json.loads(to_json(spent))).evaluations)
    second = admit(space, o.propose("simulate_pulse", *SIM), auth)  # a verification handed the spent state
    o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)  # restore (object replaced)
    try:
        gw.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        s = str(exc)
        again = "refused " + s[s.find("("):][:70]
    print(f"{label:24s} plain={plain!s:5s} owner_reads_back={owner_back} | verification on spend: "
          f"{second.status.value} {second.codes()} | after restore: {again} | executor ran {len(calls)}")
    if not plain:
        print(f"{'':24s} types in spent to_dict: {sorted(types_in(spent.to_dict(), set()))}")


for label, meta in [("no metadata", {}), ("flat {'seed': 1}", {"seed": 1}), ("nested list", {"seeds": [1, 2]}),
                    ("nested dict", {"run": {"host": "a"}}), ("tuple", {"seeds": (1, 2)})]:
    run(label, meta)


# V6: availability - an experiment whose earlier evaluation carries nested metadata, restored from JSON
o = ax.owned("battery")
eid = next(iter(o.experiments))
o.experiments[eid].record(ScientificEvaluation("pre.nested", {}, status=EvaluationStatus.NOT_CONVERGED,
                                               detail="x", metadata={"seeds": [1, 2]}))
o.experiments[eid] = ScientificExperiment.from_dict(json.loads(to_json(o.experiments[eid])))
auth = o.authorities()
res = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
print(f"V6 JSON-restored experiment with nested eval metadata: admission {res.status.value} {res.codes()}")
