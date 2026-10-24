"""README sec.4 / sec.9 claim: 'a transient failure or an interrupt with no new entry, then an honest unchanged
checkpoint restore, does not retire the account'.  Case: the last read's entries moved during its read-back (a
campaign recording meanwhile), so no entry objects are known; then a transient failure with NO new entry."""
from common import *
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
print("owners:", owners_mod.__file__)

def run(moving_read):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    key = ("experiment", eid)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    real = live.to_dict
    if moving_read:
        once = {"done": False}
        def recording_meanwhile():          # a campaign records an evaluation while this read-back serializes
            if not once["done"]:
                once["done"] = True
                live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
            return real()
        object.__setattr__(live, "to_dict", recording_meanwhile)
    else:
        live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    rec = reader.read(OwnerKind.EXPERIMENT, eid)
    print("moving_read" if moving_read else "stable_read ", "read 1 served revision", rec.revision,
          "| seen", len(reader._seen[key]), "| entries now", len(live._evaluations),
          "| seen_entries known:", key in reader._seen_entries)
    def moving():
        raise RuntimeError("dictionary changed size during iteration")
    object.__setattr__(live, "to_dict", moving)       # a transient failure, no new entry
    try:
        reader.read(OwnerKind.EXPERIMENT, eid)
        print("  read 2 served")
    except OwnerUnavailable as exc:
        print("  read 2 refused:", str(exc)[:90])
    print("  unread recorded:", {k: len(v) for k, v in reader._unread_entries.items()})
    o.experiments[eid] = ScientificExperiment.from_dict(real())     # the campaign's unchanged checkpoint resume
    try:
        print("  read 3 after an unchanged resume: served revision", reader.read(OwnerKind.EXPERIMENT, eid).revision)
    except OwnerUnavailable as exc:
        print("  read 3 after an unchanged resume REFUSED:", str(exc)[:140])
    print("  diverged:", bool(reader._diverged))

run(False)
run(True)
