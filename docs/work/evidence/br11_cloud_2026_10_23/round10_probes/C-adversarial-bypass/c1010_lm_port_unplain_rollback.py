"""R10-C c1010: c1008 end to end through the PUBLIC Mind-facing API with the execution side's normal configuration:
the fixture's own live authorities (BudgetReader.following over the execution side's mapping), a suggestions_only desk
and port, and a language-model ExternalSuggestion through proposed_action_from_suggestion.  The executor records the
run's observation as an evaluation with ordinary nested metadata; a later Mind admission request is refused (the
follower cannot read the spend); the execution side restores the experiment from its pre-run checkpoint
(ScientificExperiment.from_dict, object replaced, as sria.campaign restores); the Mind executes the same admitted
action again.  Run once with plain metadata (control) and once with nested metadata."""
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (ExecutionDesk, FeasibleActionSpace, IntakeRefusal, MindWorldPort, project_world,
                                proposed_action_from_suggestion)
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind

SIM = ax.base("battery")["simulate_pulse"]


def run(label, meta):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    auth = o.authorities()                                   # the execution side's live readers (following budget)
    calls = []

    def executor(authorization):
        calls.append(authorization.admitted_digest)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata=meta))
        return "ran"

    gw = ExecutionDesk(auth, executor, accept_synthetic=True, suggestions_only=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, auth)), suggestions_only=True)
    pw = port.world
    spec = pw.action("simulate_pulse")
    assignments, observe = SIM
    s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", spec.family, "simulate_pulse",
                           {"assignments": [{"variable": k, "value": v.to_dict()} for k, v in assignments.items()],
                            "observe": list(observe)}, "lm", extra={"world_revision": pw.revision_id})
    p = proposed_action_from_suggestion(s, world=pw)
    assert not isinstance(p, IntakeRefusal), p
    checkpoint = o.experiments[eid].to_dict()                # the execution side's pre-run checkpoint
    r = port.request_admission(p, gw)
    assert r.admitted is not None, (r.status, r.codes())
    port.execute(r.admitted, gw)                              # run 1: the executor records its evaluation
    p2 = proposed_action_from_suggestion(s, world=pw)
    later = port.request_admission(p2, gw)                    # a Mind admission request after the run
    o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)   # restore from the checkpoint
    try:
        port.execute(r.admitted, gw)
        again = "DISPATCHED AGAIN"
    except Exception as exc:  # noqa: BLE001
        again = f"refused ({type(exc).__name__}: {str(exc)[str(exc).find('('):][:60]})"
    print(f"{label:28s} | admission after the run: {later.status.value} {later.codes()} | after the restore: {again}"
          f" | executor ran {len(calls)}")


run("plain metadata (control)", {"seed": 1})
run("nested metadata", {"seeds": [1, 2]})
