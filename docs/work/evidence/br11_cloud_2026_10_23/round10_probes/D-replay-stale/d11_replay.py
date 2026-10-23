import json, sys, hashlib
from engcore.mind.world import replay_admission
from engcore.mind.repsem import canonical_bytes
recs = json.load(open(sys.argv[1]))["records"]
out = {}
for label, r in sorted(recs.items()):
    assert hashlib.sha256(canonical_bytes(r["record"])).hexdigest() == r["sha"]
    rr = replay_admission(r["record"])
    re_bytes = None if rr.recomputed is None else hashlib.sha256(canonical_bytes(rr.recomputed)).hexdigest()[:16]
    out[label] = (rr.outcome.value, r["sha"][:16], re_bytes, rr.detail[:80] if rr.outcome.value != "reproduced" else "")
print(json.dumps(out, sort_keys=True, indent=0))
