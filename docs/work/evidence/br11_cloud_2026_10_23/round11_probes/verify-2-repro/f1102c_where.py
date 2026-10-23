"""R11-F f1102c: where the read-back of a 600-deep (owner-readable) experiment raises at aad2f69."""
import traceback
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
o = ax.owned("battery")
eid = next(iter(o.experiments))
x = {"leaf": 1}
for i in range(600):
    x = {f"k{i}": x}
o.experiments[eid].metadata["trace"] = x
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments)) if False else None
try:
    BudgetReader.following(lambda: (o.ledgers, o.experiments))
    print("constructed")
except BaseException as exc:  # noqa: BLE001
    tb = traceback.extract_tb(exc.__traceback__)
    owners = [f"{f.filename.split('/')[-1]}:{f.lineno} {f.line}" for f in tb if "mind/world" in f.filename]
    print(type(exc).__name__, "| frames in mind/world:", owners[-3:])
