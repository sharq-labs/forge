import json
from collections import Counter

R = "benchmarks/mind_gen2_authority_v1/results/"
d = json.load(open(R + "BR1_RESCORE.json"))
print("RESCORE keys:", list(d.keys()))
for k, v in d.items():
    if isinstance(v, (str, int, float, bool)) or v is None:
        print(" ", k, v)
    elif isinstance(v, dict):
        print(" ", k, json.dumps(v)[:600])
    else:
        print(" ", k, "list", len(v), json.dumps(v[:1])[:300])
a = json.load(open(R + "AUTHORITY.json"))
print("AUTHORITY keys:", list(a.keys()))
for k, v in a.items():
    if isinstance(v, dict):
        print(" ", k, json.dumps(v)[:700])
    elif isinstance(v, list):
        print(" ", k, "list", len(v), json.dumps(v[:1])[:300])
    else:
        print(" ", k, v)
