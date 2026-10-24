"""a1202 detail: the depths at which the honest experiment is refused for good, the caller's headroom there, and what
the same reader then says at shallow depth (refused for good, while a new reader reads the account)."""
import sys
sys.argv = [sys.argv[0]]
exec(open(__file__.replace("a1202b_detail.py", "a1202_deep_stack_new_unit.py")).read().split("base = depth()")[0])
base = depth()
limit = sys.getrecursionlimit()
refused = []
for k, unit in zip(range(limit - base - 60, limit - base - 2), UNITS[200:]):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    o.experiments[eid].record(ScientificEvaluation(f"deep.{k}", {"x": Quantity(1.5, unit)},
                                                   status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    def deep(n):
        return deep(n - 1) if n else reader.read(OwnerKind.EXPERIMENT, eid)
    try:
        deep(k)
    except Exception as exc:
        pass
    if reader._diverged:
        try:
            reader.read(OwnerKind.EXPERIMENT, eid)
            later = "read"
        except OwnerUnavailable as exc:
            later = "shallow read by the same reader: " + ("REFUSED FOR GOOD" if "from then on" in str(exc) else "refused")
        fresh = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments))).read(OwnerKind.EXPERIMENT, eid)
        refused.append((k, limit - (base + k), unit, later, "new reader reads revision " + fresh.revision))
for r in refused:
    print("k", r[0], "caller headroom (frames below the limit)", r[1], r[2], "|", r[3], "|", r[4])
print("refused for good at", len(refused), "of 58 depths")
